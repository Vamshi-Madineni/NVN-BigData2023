import asyncio
from datetime import datetime, timedelta
import elasticsearch
import json
import logging
import os
import re
import sodapy
import time

from datamart_core import Discoverer


logger = logging.getLogger(__name__)


re_non_id_safe = re.compile(r'[^a-z0-9-]+')


def encode_domain(url):
    domain = re_non_id_safe.sub('-', url.lower())
    return domain


class SocrataDiscoverer(Discoverer):
    DEFAULT_DOMAINS = [
        {'url': 'data.cityofnewyork.us'},
        {'url': 'finances.worldbank.org'},
    ]
    CHECK_INTERVAL = timedelta(days=1)

    def __init__(self, *args, **kwargs):
        super(SocrataDiscoverer, self).__init__(*args, **kwargs)

        if os.path.exists('socrata.json'):
            with open('socrata.json') as fp:
                self.domains = json.load(fp)
            logger.info("Loaded %d domains from socrata.json",
                        len(self.domains))
        else:
            self.domains = self.DEFAULT_DOMAINS
            logger.info("Using default domains")

        self.last_update = {}

    def main_loop(self):
        while True:
            sleep_until = None
            now = datetime.utcnow()
            for domain in self.domains:
                last_update = self.last_update.get(domain['url'])
                interval = domain.get('check_interval', self.CHECK_INTERVAL)
                if last_update is None or last_update + interval < now:
                    try:
                        self.process_domain(domain)
                    except Exception:
                        logger.exception("Error processing %s", domain['url'])
                    self.last_update[domain['url']] = now
                    if sleep_until is None or sleep_until > now + interval:
                        sleep_until = now + interval

            while datetime.utcnow() < sleep_until:
                time.sleep((sleep_until - datetime.utcnow()).total_seconds())

    def process_domain(self, domain):
        logger.info("Processing %s...", domain['url'])
        socrata = sodapy.Socrata(domain['url'],
                                 **domain.get('auth', {'app_token': None}))
        datasets = socrata.datasets()
        logger.info("Found %d datasets", len(datasets))
        for dataset in datasets:
            try:
                self.process_dataset(domain, dataset)
            except Exception:
                logger.exception("Error processing dataset %s",
                                 dataset['resource']['id'])

    def process_dataset(self, domain, dataset):
        # Get metadata
        resource = dataset['resource']
        id = resource['id']

        # Check type
        # api, calendar, chart, datalens, dataset, federated_href, file,
        # filter, form, href, link, map, measure, story, visualization
        if resource['type'] != 'dataset':
            logger.info("Skipping %s, type %s", id, resource['type'])
            return

        # Get record from Elasticsearch
        try:
            hit = self.elasticsearch.get(
                'datamart', '_doc',
                '%s.%s' % (self.identifier, id),
                _source=['materialize.socrata_updated'])
        except elasticsearch.NotFoundError:
            pass
        else:
            updated = hit['_source']['materialize']['socrata_updated']
            if resource['updatedAt'] <= updated:
                logger.info("Dataset has not changed: %s", id)
                return

        # Read metadata
        metadata = dict(
            name=resource.get('name', id),
        )
        if resource.get('description'):
            metadata['description'] = resource['description']
        direct_url = (
            'https://{domain}/api/views/{dataset_id}/rows.csv'
            '?accessType=DOWNLOAD'.format(domain=domain['url'], dataset_id=id)
        )

        # Discover this dataset
        encoded_domain = encode_domain(domain['url'])
        self.record_dataset(dict(socrata_id=id,
                                 socrata_domain=domain['url'],
                                 socrata_updated=resource['updatedAt'],
                                 direct_url=direct_url),
                            metadata,
                            dataset_id='{}.{}'.format(encoded_domain, id))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s")
    SocrataDiscoverer('datamart.socrata')
    asyncio.get_event_loop().run_forever()