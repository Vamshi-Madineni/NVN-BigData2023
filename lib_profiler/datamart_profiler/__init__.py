import codecs
import contextlib
import json
import logging
import math
import numpy
import os
import pandas
import pkg_resources
import prometheus_client
import random
from sklearn.cluster import KMeans
import subprocess

from datamart_core.common import Type

from .types import identify_types


logger = logging.getLogger(__name__)


MAX_SIZE = 50_000_000


BUCKETS = [0.5, 1.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0, 300.0, 600.0]

PROM_PROFILE = prometheus_client.Histogram('profile_seconds',
                                           "Profile time",
                                           buckets=BUCKETS)
PROM_TYPES = prometheus_client.Histogram('profile_types_seconds',
                                         "Profile types time",
                                         buckets=BUCKETS)
PROM_SPATIAL = prometheus_client.Histogram('profile_spatial_seconds',
                                           "Profile spatial coverage time",
                                           buckets=BUCKETS)


def mean_stddev(array):
    total = 0
    for elem in array:
        if elem is not None:
            total += elem
    mean = total / len(array)if len(array) > 0 else 0
    total = 0
    for elem in array:
        if elem is not None:
            elem = elem - mean
            total += elem * elem
    stddev = math.sqrt(total / len(array)) if len(array) > 0 else 0

    return mean, stddev


N_RANGES = 3


def get_numerical_ranges(values):
    """
    Retrieve the numeral ranges given the input (timestamp, integer, or float).

    This performs K-Means clustering, returning a maximum of 3 ranges.
    """

    if not values:
        return []

    logger.info("Computing numerical ranges, %d values", len(values))

    clustering = KMeans(n_clusters=min(N_RANGES, len(values)),
                        random_state=0)
    clustering.fit(numpy.array(values).reshape(-1, 1))
    logger.info("K-Means clusters: %r", clustering.cluster_centers_)

    # Compute confidence intervals for each range
    ranges = []
    sizes = []
    for rg in range(N_RANGES):
        cluster = [values[i]
                   for i in range(len(values))
                   if clustering.labels_[i] == rg]
        if not cluster:
            continue
        cluster.sort()
        min_idx = int(0.05 * len(cluster))
        max_idx = int(0.95 * len(cluster))
        ranges.append([
            cluster[min_idx],
            cluster[max_idx],
        ])
        sizes.append(len(cluster))
    logger.info("Ranges: %r", ranges)
    logger.info("Sizes: %r", sizes)

    # Convert to Elasticsearch syntax
    ranges = [{'range': {'gte': rg[0], 'lte': rg[1]}}
              for rg in ranges]
    return ranges


SPATIAL_RANGE_DELTA_LONG = 0.0001
SPATIAL_RANGE_DELTA_LAT = 0.0001


def get_spatial_ranges(values):
    """
    Retrieve the spatial ranges (i.e. bounding boxes) given the input gps points.

    This performs K-Means clustering, returning a maximum of 3 ranges.
    """

    clustering = KMeans(n_clusters=min(N_RANGES, len(values)),
                        random_state=0)
    clustering.fit(values)
    logger.info("K-Means clusters: %r", clustering.cluster_centers_)

    # Compute confidence intervals for each range
    ranges = []
    sizes = []
    for rg in range(N_RANGES):
        cluster = [values[i]
                   for i in range(len(values))
                   if clustering.labels_[i] == rg]
        if not cluster:
            continue
        cluster.sort(key=lambda p: p[0])
        min_idx = int(0.05 * len(cluster))
        max_idx = int(0.95 * len(cluster))
        min_lat = cluster[min_idx][0]
        max_lat = cluster[max_idx][0]
        cluster.sort(key=lambda p: p[1])
        min_long = cluster[min_idx][1]
        max_long = cluster[max_idx][1]
        ranges.append([
            [min_long, max_lat],
            [max_long, min_lat],
        ])
        sizes.append(len(cluster))
    logger.info("Ranges: %r", ranges)
    logger.info("Sizes: %r", sizes)

    # Lucene needs shapes to have an area for tessellation (no point or line)
    for rg in ranges:
        if rg[0][0] == rg[1][0]:
            rg[0][0] -= SPATIAL_RANGE_DELTA_LONG
            rg[1][0] += SPATIAL_RANGE_DELTA_LONG
        if rg[0][1] == rg[1][1]:
            rg[0][1] += SPATIAL_RANGE_DELTA_LAT
            rg[1][1] -= SPATIAL_RANGE_DELTA_LAT

    # TODO: Deal with clusters made of outliers

    # Convert to Elasticsearch syntax
    ranges = [{'range': {'type': 'envelope',
                         'coordinates': coords}}
              for coords in ranges]
    return ranges


def run_scdp(data):
    # Run SCDP
    logger.info("Running SCDP...")
    scdp = pkg_resources.resource_filename('datamart_profiler', 'scdp.jar')
    if isinstance(data, (str, bytes)):
        if os.path.isdir(data):
            data = os.path.join(data, 'main.csv')
        if not os.path.exists(data):
            raise ValueError("data file does not exist")
        proc = subprocess.Popen(['java', '-jar', scdp, data],
                                stdout=subprocess.PIPE,
                                stdin=subprocess.PIPE)
        stdout, _ = proc.communicate()
    else:
        proc = subprocess.Popen(['java', '-jar', scdp, '/dev/stdin'],
                                stdout=subprocess.PIPE,
                                stdin=subprocess.PIPE)
        data.to_csv(codecs.getwriter('utf-8')(proc.stdin))
        stdout, _ = proc.communicate()
    if proc.wait() != 0:
        logger.error("Error running SCDP: returned %d", proc.returncode)
        return {}
    else:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            logger.exception("Invalid output from SCDP")
            return {}


def normalize_latlong_column_name(name, *substrings):
    name = name.lower()
    for substr in substrings:
        idx = name.find(substr)
        if idx >= 0:
            name = name[:idx] + name[idx + len(substr):]
            break
    return name


def pair_latlong_columns(columns_lat, columns_long):
    # Normalize latitude column names
    normalized_lat = {}
    for i, (name, values_lat) in enumerate(columns_lat):
        name = normalize_latlong_column_name(name, 'latitude', 'lat')
        normalized_lat[name] = i

    # Go over normalized longitude column names and try to match
    pairs = []
    missed_long = []
    for name, values_long in columns_long:
        norm_name = normalize_latlong_column_name(name, 'longitude', 'long')
        if norm_name in normalized_lat:
            pairs.append((columns_lat[normalized_lat.pop(norm_name)],
                          (name, values_long)))
        else:
            missed_long.append(name)

    # Gather missed columns and log them
    missed_lat = [columns_lat[i][0] for i in sorted(normalized_lat.values())]
    if missed_lat:
        logger.warning("Unmatched latitude columns: %r", missed_lat)
    if missed_long:
        logger.warning("Unmatched longitude columns: %r", missed_long)

    return pairs


@PROM_PROFILE.time()
def process_dataset(data, dataset_id=None, metadata=None,
                    lazo_client=None, search=False):
    """Compute all metafeatures from a dataset.

    :param data: path to dataset
    :param dataset_id: id of the dataset
    :param metadata: The metadata provided by the discovery plugin (might be
        very limited).
    :param lazo_client: client for the Lazo Index Server
    :param search: True if this method is being called during the search
        operation (and not for indexing).
    """
    if metadata is None:
        metadata = {}

    # FIXME: SCDP currently disabled
    # scdp_out = run_scdp(data)
    scdp_out = {}

    data_path = None
    if isinstance(data, pandas.DataFrame):
        metadata['nb_rows'] = len(data)
        # FIXME: no sampling here!
    else:
        with contextlib.ExitStack() as stack:
            if isinstance(data, (str, bytes)):
                if not os.path.exists(data):
                    raise ValueError("data file does not exist")

                # saving path
                data_path = data

                # File size
                metadata['size'] = os.path.getsize(data)
                logger.info("File size: %r bytes", metadata['size'])

                data = stack.enter_context(open(data, 'rb'))
            elif hasattr(data, 'read'):
                # Get size by seeking to the end
                data.seek(0, 2)
                metadata['size'] = data.tell()
                data.seek(0, 0)
            else:
                raise TypeError("data should be a filename, a file object, or "
                                "a pandas.DataFrame")

            # Sub-sample
            if metadata['size'] > MAX_SIZE:
                logger.info("Counting rows...")
                metadata['nb_rows'] = sum(1 for _ in data)
                data.seek(0, 0)

                ratio = MAX_SIZE / metadata['size']
                logger.info("Loading dataframe, sample ratio=%r...", ratio)
                data = pandas.read_csv(
                    data,
                    dtype=str, na_filter=False,
                    skiprows=lambda i: i != 0 and random.random() > ratio)
            else:
                logger.info("Loading dataframe...")
                data = pandas.read_csv(data,
                                       dtype=str, na_filter=False)

                metadata['nb_rows'] = data.shape[0]

            logger.info("Dataframe loaded, %d rows, %d columns",
                        data.shape[0], data.shape[1])

    # Get column dictionary
    columns = metadata.setdefault('columns', [])
    # Fix size if wrong
    if len(columns) != len(data.columns):
        logger.info("Setting column names from header")
        columns[:] = [{} for _ in range(len(data.columns))]
    else:
        logger.info("Keeping columns from discoverer")

    # Set column names
    for column_meta, name in zip(columns, data.columns):
        column_meta['name'] = name

    # Copy info from SCDP
    for column_meta, name in zip(columns, data.columns):
        column_meta.update(scdp_out.get(name, {}))

    # Lat / Long
    columns_lat = []
    columns_long = []

    # Textual columns
    column_textual = []

    # Identify types
    logger.info("Identifying types...")
    with PROM_TYPES.time():
        for i, column_meta in enumerate(columns):
            logger.info("Processing column %d...", i)
            array = data.iloc[:, i]
            # Identify types
            structural_type, semantic_types_dict, additional_meta = \
                identify_types(array, column_meta['name'])
            # Set structural type
            column_meta['structural_type'] = structural_type
            # Add semantic types to the ones already present
            sem_types = column_meta.setdefault('semantic_types', [])
            for sem_type in semantic_types_dict:
                if sem_type not in sem_types:
                    sem_types.append(sem_type)
            # Insert additional metadata
            column_meta.update(additional_meta)

            # Compute ranges for numerical/spatial data
            if structural_type in (Type.INTEGER, Type.FLOAT):
                # Get numerical ranges
                numerical_values = []
                for e in array:
                    try:
                        e = float(e)
                    except ValueError:
                        e = None
                    else:
                        if not (-3.4e38 < e < 3.4e38):  # Overflows in ES
                            e = None
                    numerical_values.append(e)

                column_meta['mean'], column_meta['stddev'] = \
                    mean_stddev(numerical_values)

                # Get lat/long columns
                if Type.LATITUDE in semantic_types_dict:
                    columns_lat.append(
                        (column_meta['name'], numerical_values)
                    )
                elif Type.LONGITUDE in semantic_types_dict:
                    columns_long.append(
                        (column_meta['name'], numerical_values)
                    )
                else:
                    ranges = get_numerical_ranges(
                        [x for x in numerical_values if x is not None]
                    )
                    if ranges:
                        column_meta['coverage'] = ranges

            # Compute ranges for temporal data
            if Type.DATE_TIME in semantic_types_dict:
                timestamps = numpy.empty(
                    len(semantic_types_dict[Type.DATE_TIME]),
                    dtype='float32',
                )
                timestamps_for_range = []
                for j, dt in enumerate(
                        semantic_types_dict[Type.DATE_TIME]):
                    timestamps[j] = dt.timestamp()
                    timestamps_for_range.append(
                        dt.replace(minute=0, second=0).timestamp()
                    )
                column_meta['mean'], column_meta['stddev'] = \
                    mean_stddev(timestamps)

                # Get temporal ranges
                ranges = get_numerical_ranges(timestamps_for_range)
                if ranges:
                    column_meta['coverage'] = ranges

            if structural_type == Type.TEXT and \
                    Type.DATE_TIME not in semantic_types_dict:
                column_textual.append(column_meta['name'])

    # Textual columns
    if lazo_client and column_textual:
        # Indexing with lazo
        if not search:
            logger.info("Indexing textual data with Lazo...")
            try:
                if data_path:
                    # if we have the path, send the path
                    lazo_client.index_data_path(
                        data_path,
                        dataset_id,
                        column_textual
                    )
                else:
                    # if path is not available, send the data instead
                    for column_name in column_textual:
                        lazo_client.index_data(
                            data[column_name].values.tolist(),
                            dataset_id,
                            column_name
                        )
            except Exception as e:
                logger.warning('Error indexing textual attributes from %s', dataset_id)
                logger.warning(str(e))
        # Generating Lazo sketches for the search
        else:
            logger.info("Generating Lazo sketches...")
            try:
                if data_path:
                    # if we have the path, send the path
                    lazo_sketches = lazo_client.get_lazo_sketch_from_data_path(
                        data_path,
                        "",
                        column_textual
                    )
                else:
                    # if path is not available, send the data instead
                    lazo_sketches = []
                    for column_name in column_textual:
                        lazo_sketches.append(
                            lazo_client.get_lazo_sketch_from_data(
                                data[column_name].values.tolist(),
                                "",
                                column_name
                            )
                        )
                # saving sketches into metadata
                metadata_lazo = []
                for i in range(len(column_textual)):
                    n_permutations, hash_values, cardinality =\
                        lazo_sketches[i]
                    metadata_lazo.append(dict(
                        name=column_textual[i],
                        n_permutations=n_permutations,
                        hash_values=list(hash_values),
                        cardinality=cardinality
                    ))
                metadata['lazo'] = metadata_lazo
            except Exception as e:
                logger.warning('Error getting Lazo sketches textual attributes from %s', dataset_id)
                logger.warning(str(e))

    # Lat / Lon
    logger.info("Computing spatial coverage...")
    with PROM_SPATIAL.time():
        spatial_coverage = []
        pairs = pair_latlong_columns(columns_lat, columns_long)
        for (name_lat, values_lat), (name_long, values_long) in pairs:
            values = []
            for lat, long in zip(values_lat, values_long):
                if (lat and long and  # Ignore None and 0
                        -90 < lat < 90 and -180 < long < 180):
                    values.append((lat, long))

            if len(values) > 1:
                logger.info("Computing spatial ranges %r,%r (%d rows)",
                            name_lat, name_long, len(values))
                spatial_ranges = get_spatial_ranges(values)
                if spatial_ranges:
                    spatial_coverage.append({"lat": name_lat,
                                             "lon": name_long,
                                             "ranges": spatial_ranges})

    if spatial_coverage:
        metadata['spatial_coverage'] = spatial_coverage

    # Return it -- it will be inserted into Elasticsearch, and published to the
    # feed and the waiting on-demand searches
    return metadata
