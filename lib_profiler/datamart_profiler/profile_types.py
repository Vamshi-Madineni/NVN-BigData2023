from datetime import datetime
import dateutil.tz
import re
import regex

from . import types
from .temporal import parse_date


_re_int = re.compile(
    r'^[+-]?[0-9]+'
    r'(?:\.0*)?'  # 4.0 and 7.000 are integers
    r'$'
)
_re_float = re.compile(
    r'^[+-]?'
    r'(?:'
    r'(?:[0-9]+\.[0-9]*)|'
    r'(?:\.[0-9]+)'
    r')'
    r'(?:[Ee][0-9]+)?$'
)
_re_wkt_point = re.compile(
    r'^POINT ?\('
    r'-?[0-9]{1,3}\.[0-9]{1,15}'
    r' '
    r'-?[0-9]{1,3}\.[0-9]{1,15}'
    r'\)$'
)
_re_wkt_polygon = re.compile(
    r'^POLYGON ?\('
    r'('
    r'\([0-9 .]+\)'
    r', ?)*'
    r'\([0-9 .]+\)'
    r'\)$'
)
_re_geo_combined = regex.compile(
    r'^([\p{Lu}\p{Po}0-9 ])+ \('
    r'-?[0-9]{1,3}\.[0-9]{1,15}'
    r', ?'
    r'-?[0-9]{1,3}\.[0-9]{1,15}'
    r'\)$'
)
_re_whitespace = re.compile(r'\s')


# Tolerable ratio of unclean data
MAX_UNCLEAN = 0.02  # 2%


# Maximum number of different values for categorical columns
MAX_CATEGORICAL_RATIO = 0.10  # 10%

def regular_exp_count(array, num_total):
    # Let you check/count how many instances match a structure of a data type
    types = ['num_float', 'num_int', 'num_bool', 'num_empty', 'num_point', 'num_geo_combined', 'num_polygon', 'num_text']
    re_count = {el:0 for el in types}

    for elem in array:
        if not elem:
            re_count['num_empty'] += 1
        elif _re_int.match(elem):
            re_count['num_int'] += 1
        elif _re_float.match(elem):
            re_count['num_float'] += 1
        elif _re_wkt_point.match(elem):
            re_count['num_point'] += 1
        elif _re_geo_combined.match(elem):
            re_count['num_geo_combined'] += 1
        elif _re_wkt_polygon.match(elem):
            re_count['num_polygon'] += 1
        elif len(_re_whitespace.findall(elem)) >= 4:
            re_count['num_text'] += 1
        if elem.lower() in ('0', '1', 'true', 'false', 'y', 'n', 'yes', 'no'):
            re_count['num_bool'] += 1

    return re_count

def unclean_values_ratio(c_type, re_count, num_total):
    ratio = 0
    if c_type == types.INTEGER:
        ratio = \
            (num_total - re_count['num_empty'] - re_count['num_int']) / num_total
    if c_type == types.FLOAT:
        ratio = \
            (num_total - re_count['num_empty'] - re_count['num_int'] - re_count['num_float']) / num_total
    if c_type == types.GEO_POINT:
        ratio = \
            (num_total - re_count['num_empty'] - re_count['num_point']) / num_total
    if c_type == types.GEO_POLYGON:
        ratio = \
            (num_total - re_count['num_empty'] - re_count['num_polygon']) / num_total
    if c_type == types.BOOLEAN:
        ratio = \
            (num_total - re_count['num_empty'] - re_count['num_bool']) / num_total
    return ratio

def parse_dates(array):
    parsed_dates = []
    for elem in array:
        elem = parse_date(elem)
        if elem is not None:
            parsed_dates.append(elem)
    return parsed_dates

def identify_structural_type(re_count, num_total, threshold):
    if re_count['num_empty'] == num_total:
        structural_type = types.MISSING_DATA
    elif re_count['num_int'] >= threshold:
        structural_type = types.INTEGER
    elif re_count['num_int'] + re_count['num_float'] >= threshold:
        structural_type = types.FLOAT
    elif re_count['num_point'] >= threshold or re_count['num_geo_combined'] >= threshold:
        structural_type = types.GEO_POINT
    elif re_count['num_polygon'] >= threshold:
        structural_type = types.GEO_POLYGON
    elif re_count['num_polygon'] >= threshold:
        structural_type = types.GEO_POLYGON
    else:
        structural_type = types.TEXT

    return structural_type

def get_dates(array, resolution):
    dates = []
    for el in array:
        try:
            if resolution == 'year':
                dates.append(datetime(
                    int(el), 1, 1,
                    tzinfo=dateutil.tz.UTC,
                ))
            if resolution == 'month':
                dates.append(datetime(
                    0, int(el), 1,
                    tzinfo=dateutil.tz.UTC,
                ))
            if resolution == 'day':
                dates.append(datetime(
                    0, 0, int(el),
                    tzinfo=dateutil.tz.UTC,
                ))
        except ValueError:
            pass
    return dates

def identify_types(array, name, geo_data, updateColumn):
    num_total = len(array)
    column_meta = {}
    # Human-In-the-Loop feedback
    is_HIL_feedback = True if len(updateColumn) > 0  else False

    # This function let you check/count how many instances match a structure of particular data type
    re_count = regular_exp_count(array, num_total)

    # Identify structural type and compute unclean values ratio
    threshold = max(1, (1.0 - MAX_UNCLEAN) * (num_total - re_count['num_empty']))
    if is_HIL_feedback:
        structural_type = updateColumn[0]['structural_type']
        column_meta['unclean_values_ratio'] = unclean_values_ratio(structural_type, re_count, num_total)
    else:
        structural_type = identify_structural_type(re_count, num_total, threshold)
        column_meta['unclean_values_ratio'] = unclean_values_ratio(structural_type, re_count, num_total)

    # compute missing values ratio
    if structural_type != types.MISSING_DATA and re_count['num_empty'] > 0:
        column_meta['missing_values_ratio'] = re_count['num_empty'] / num_total

    # TODO: structural or semantic types?
    semantic_types_dict = {}
    if is_HIL_feedback:
        semantic_types = updateColumn[0]['semantic_types']
        semantic_types_dict = {el:None for el in semantic_types}

        for el in semantic_types:
            if el == types.BOOLEAN:
                column_meta['unclean_values_ratio'] = \
                    unclean_values_ratio(types.BOOLEAN, re_count, num_total)
            if (el == types.LATITUDE or el == types.LONGITUDE) and 'latlong_pair' in updateColumn[0]:
                    column_meta['latlong_pair'] = updateColumn[0]['latlong_pair']
            if el == types.DATE_TIME:
                if 'temporal_resolution' in updateColumn[0]:
                    resolution = updateColumn[0]['temporal_resolution']
                    dates = get_dates(array, resolution)
                    column_meta['temporal_resolution'] = resolution
                else:
                    dates = parse_dates(array)
                semantic_types_dict[types.DATE_TIME] = dates
            if el == types.ADMIN:
                if geo_data is not None:
                    resolved = geo_data.resolve_names(array)
                    if sum(1 for r in resolved if r is not None) > 0.7 * len(array):
                        semantic_types_dict[types.ADMIN] = resolved
            if el == types.CATEGORICAL or el == types.INTEGER:
                # Count distinct values
                values = set(e for e in array if e)
                column_meta['num_distinct_values'] = len(values)
                if el == types.CATEGORICAL:
                    semantic_types_dict[types.CATEGORICAL] = values
    else:
        # Identify booleans
        num_bool = re_count['num_bool']
        num_text = re_count['num_text']
        num_empty = re_count['num_empty']

        if num_bool >= threshold:
            semantic_types_dict[types.BOOLEAN] = None
            column_meta['unclean_values_ratio'] = \
                unclean_values_ratio(types.BOOLEAN, re_count, num_total)

        if structural_type == types.TEXT:
            categorical = False

            if geo_data is not None:
                resolved = geo_data.resolve_names(array)
                if sum(1 for r in resolved if r is not None) > 0.7 * len(array):
                    semantic_types_dict[types.ADMIN] = resolved
                    categorical = True

            if not categorical and num_text >= threshold:
                # Free text
                semantic_types_dict[types.TEXT] = None
            else:
                # Count distinct values
                values = set(e for e in array if e)
                column_meta['num_distinct_values'] = len(values)
                max_categorical = MAX_CATEGORICAL_RATIO * (len(array) - num_empty)
                if (
                    categorical or
                    len(values) <= max_categorical or
                    types.BOOLEAN in semantic_types_dict
                ):
                    semantic_types_dict[types.CATEGORICAL] = values
        elif structural_type == types.INTEGER:
            # Identify ids
            # TODO: is this enough?
            # TODO: what about false positives?
            if (name.lower().startswith('id') or
                    name.lower().endswith('id') or
                    name.lower().startswith('identifier') or
                    name.lower().endswith('identifier') or
                    name.lower().startswith('index') or
                    name.lower().endswith('index')):
                semantic_types_dict[types.ID] = None

            # Count distinct values
            values = set(e for e in array if e)
            column_meta['num_distinct_values'] = len(values)

            # Identify years
            if name.strip().lower() == 'year':
                dates = get_dates(array, 'year')
                if len(dates) >= threshold:
                    semantic_types_dict[types.DATE_TIME] = dates

        # Identify lat/long
        if structural_type == types.FLOAT:
            num_lat = num_long = 0
            for elem in array:
                try:
                    elem = float(elem)
                except ValueError:
                    pass
                else:
                    if -180.0 <= float(elem) <= 180.0:
                        num_long += 1
                        if -90.0 <= float(elem) <= 90.0:
                            num_lat += 1

            if num_lat >= threshold and 'lat' in name.lower():
                semantic_types_dict[types.LATITUDE] = None
            if num_long >= threshold and 'lon' in name.lower():
                semantic_types_dict[types.LONGITUDE] = None

        # Identify dates
        parsed_dates = parse_dates(array)

        if len(parsed_dates) >= threshold:
            semantic_types_dict[types.DATE_TIME] = parsed_dates
            if structural_type == types.INTEGER:
                # 'YYYYMMDD' format means values can be parsed as integers, but
                # that's not what they are
                structural_type = types.TEXT

    return structural_type, semantic_types_dict, column_meta
