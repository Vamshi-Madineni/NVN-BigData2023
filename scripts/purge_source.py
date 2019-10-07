#!/usr/bin/env python3

"""This script deletes all the datasets in the index from a specific source.
"""

import elasticsearch
import lazo_index_service
import logging
import os
import sys

from datamart_core.common import delete_dataset_from_index


SIZE = 10000


def clear(identifier):
    es = elasticsearch.Elasticsearch(
        os.environ['ELASTICSEARCH_HOSTS'].split(',')
    )
    lazo_client = lazo_index_service.LazoIndexClient(
        host=os.environ['LAZO_SERVER_HOST'],
        port=int(os.environ['LAZO_SERVER_PORT'])
    )
    from_ = 0
    while True:
        hits = es.search(
            index='datamart',
            body={
                'query': {
                    'term': {
                        'materialize.identifier': identifier,
                    },
                },
            },
            _source=False,
            from_=from_,
            size=SIZE,
        )['hits']['hits']
        from_ += len(hits)
        for h in hits:
            delete_dataset_from_index(es, h['_id'], lazo_client)
        if len(hits) != SIZE:
            break


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    clear(sys.argv[1])
