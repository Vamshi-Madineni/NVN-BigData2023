import asyncio
import contextlib
from datetime import datetime, timedelta
import elasticsearch.helpers
import hashlib
import logging
import os
import pandas
import requests
import sentry_sdk
import tarfile
import tempfile
import time

from datamart_core import Discoverer
from datamart_core.common import setup_logging


logger = logging.getLogger(__name__)


class IsiDiscoverer(Discoverer):
    CHECK_INTERVAL = timedelta(days=1)

    def __init__(self, *args, **kwargs):
        super(IsiDiscoverer, self).__init__(*args, **kwargs)
        self.isi_endpoint = os.environ['ISI_DATAMART_URL'].rstrip('/')

    def main_loop(self):
        while True:
            now = datetime.utcnow()

            try:
                self.get_datasets()
            except Exception as e:
                sentry_sdk.capture_exception(e)
                logger.exception("Error getting datasets")

            sleep_until = now + self.CHECK_INTERVAL
            logger.info("Sleeping until %s", sleep_until.isoformat())
            while datetime.utcnow() < sleep_until:
                time.sleep((sleep_until - datetime.utcnow()).total_seconds())

    def get_datasets(self):
        # Get previous SHA-1
        try:
            info = self.elasticsearch.get(
                'pending',
                self.identifier,
            )['_source']
        except elasticsearch.NotFoundError:
            previous_sha1 = None
        else:
            previous_sha1 = info['sha1']

        # Download dump and hash it
        sha1_hasher = hashlib.sha1()
        with contextlib.ExitStack() as data_dump:
            tarball = data_dump.enter_context(
                tempfile.NamedTemporaryFile(suffix='.tar.gz')
            )
            logger.info("Downloading data dump")
            with requests.get(
                self.isi_endpoint + '/datasets/bulk',
                stream=True,
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_content(4096):
                    sha1_hasher.update(chunk)
                    tarball.write(chunk)
                tarball.flush()

            # Get digest, stop if it hasn't changed
            current_sha1 = sha1_hasher.hexdigest()
            if current_sha1 == previous_sha1:
                logger.info("Dump hasn't changed")
                return

            # Extract the tarball
            logger.info("Extracting dump")
            with data_dump.pop_all():
                folder = data_dump.enter_context(
                    tempfile.TemporaryDirectory()
                )
                with tarfile.open(tarball.name, 'r') as tar:
                    tar.extractall(folder)
                folder = os.path.join(folder, 'datamart-dump')

            seen = set()

            response = requests.get(self.isi_endpoint + '/metadata/datasets')
            response.raise_for_status()
            for dataset in response.json():
                seen.add(dataset['dataset_id'])
                try:
                    self.process_dataset(dataset, folder)
                except Exception as e:
                    sentry_sdk.capture_exception(e)
                    logger.exception(
                        "Error processing dataset %r",
                        dataset.get('dataset_id'),
                    )

            # Clean up the datasets we didn't see
            deleted = 0
            size = 10000
            query = {
                'query': {
                    'term': {
                        'materialize.identifier': self.identifier,
                    },
                },
            }
            hits = elasticsearch.helpers.scan(
                self.elasticsearch,
                index='datamart',
                query=query,
                size=size,
                _source=['materialize.isi_dataset_id'],
            )
            for h in hits:
                if h['_source']['materialize']['isi_dataset_id'] not in seen:
                    self.delete_dataset(full_id=h['_id'])
                    deleted += 1

            if deleted:
                logger.info("Deleted %d missing datasets", deleted)

            # Update SHA-1 in database
            self.elasticsearch.index(
                'pending',
                {'sha1': current_sha1},
                id=self.identifier,
            )

    def process_dataset(self, dataset, data_folder):
        dataset_id = dataset['dataset_id']
        logger.info("Processing dataset %r", dataset_id)

        # Load CSV
        data = pandas.read_csv(
            os.path.join(data_folder, dataset_id + '.csv'),
            dtype=str,
            na_filter=False,
        )
        if list(data.columns) != [
            'dataset_id', 'variable_id', 'variable',
            'main_subject', 'main_subject_id',
            'value', 'value_unit',
            'time', 'time_precision',
            'country', 'country_id', 'admin1', 'admin2', 'admin3',
            'region_coordinate',
            'stated_in', 'stated_in_id', 'stated in',
        ]:
            logger.error("Unexpected columns: %r", list(data.columns))

        # Make a single column 'name (unit)'
        data['Variable'] = data.apply(
            lambda row: (
                row['variable']
                + (' (%s)' % row['value_unit'] if row['value_unit'] else '')
            ),
            axis=1,
        )

        # Drop columns
        data = data.drop(
            [
                'dataset_id',
                'variable', 'variable_id', 'value_unit',
                'region_coordinate',
            ] + [c for c in data.columns if c.startswith('stated')],
            axis=1,
        )

        # Pivot
        data = data.pivot_table(
            index=[
                'time', 'time_precision',
                'main_subject', 'main_subject_id',
                'country', 'country_id', 'admin1', 'admin2', 'admin3',
            ],
            columns=['Variable'],
            values='value',
            aggfunc='first',
        )
        data = data.fillna('')

        # Measure sparsity
        num_na = num_total = 0
        for i in range(len(data.columns)):
            num_na += (data.iloc[:, i] == '').sum()
            num_total += len(data)
        if num_na > 0.9 * num_total:
            logger.warning("Dataset too sparse, not recording")
            return

        # Discover
        logger.info("Writing CSV")
        with self.write_to_shared_storage(dataset_id) as tmp:
            data.to_csv(
                os.path.join(tmp, 'main.csv'),
                index=True,
                line_terminator='\r\n',
            )

        self.record_dataset(
            dict(
                isi_dataset_id=dataset_id,
                isi_source_url=dataset['url'],
            ),
            dict(
                name=dataset['name'],
                source='ISI',
            ),
            dataset_id,
        )


if __name__ == '__main__':
    setup_logging()
    IsiDiscoverer('datamart.isi')
    asyncio.get_event_loop().run_forever()