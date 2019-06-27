# -*- coding: utf-8 -*-
import asyncio
import json

import certifi

from tornado.httpclient import AsyncHTTPClient, HTTPError

from .Exceptions import ServiceNotFound
from .utils.HttpUtils import HttpUtils


class GraphQLAPI:

    @classmethod
    async def get_by_alias(cls, logger, alias, tag):
        query = """
        query GetAlias($alias: Alias! $tag: String!){
          serviceByAlias(alias: $alias){
            pullUrl
            serviceTags(condition: {tag: $tag} first:1){
              nodes{
                configuration
              }
            }
          }
        }
        """

        client = AsyncHTTPClient()
        kwargs = {
            'headers': {'Content-Type': 'application/json'},
            'method': 'POST',
            'body': json.dumps({
                'query': query,
                'variables': {
                    'alias': alias,
                    'tag': tag
                }
            }),
            'ca_certs': certifi.where()
        }

        res = await cls._fetch_res_with_infinite_retry(logger, client, kwargs)

        graph_result = json.loads(res.body)

        res = graph_result['data']['serviceByAlias']
        if not res:
            raise ServiceNotFound(service=alias, tag=tag)

        return (
            res['pullUrl'],
            res['serviceTags']['nodes'][0]['configuration']
        )

    @classmethod
    async def get_by_slug(cls, logger, image, tag):
        owner, service = image.split('/')
        query = """
        query GetAlias($owner: Username!, $service: Alias!, $tag: String!) {
          allOwners(condition: {username: $owner}, first: 1) {
            nodes {
              services(condition: {name: $service}, first: 1) {
                nodes {
                  pullUrl
                  serviceTags(condition: {tag: $tag}, first: 1) {
                    nodes {
                      configuration
                    }
                  }
                }
              }
            }
          }
        }
        """

        client = AsyncHTTPClient()

        kwargs = {
            'headers': {'Content-Type': 'application/json'},
            'method': 'POST',
            'body': json.dumps({
                'query': query,
                'variables': {
                    'owner': owner,
                    'service': service,
                    'tag': tag
                }
            }),
            'ca_certs': certifi.where()
        }

        res = await cls._fetch_res_with_infinite_retry(logger, client, kwargs)

        graph_result = json.loads(res.body)
        if len(graph_result['data']['allOwners']['nodes']) == 0 \
                or len(graph_result['data']['allOwners']['nodes']
                       [0]['services']['nodes']) == 0:
            raise ServiceNotFound(service=image, tag=tag)

        res = \
            graph_result['data']['allOwners']['nodes'][0][
                'services']['nodes'][0]
        assert res, f'Slug "{image}" was not found in the Asyncy Hub'
        return (
            res['pullUrl'],
            res['serviceTags']['nodes'][0]['configuration']
        )

    @classmethod
    async def _fetch_res_with_infinite_retry(cls, logger,
                                             client, kwargs):
        res = None
        while res is None:
            try:
                res = await HttpUtils.fetch_with_retry(
                    10, logger, 'https://api.asyncy.com/graphql', client,
                    kwargs)
            except HTTPError as e:
                await asyncio.sleep(0.5)
                logger.debug(f'Retrying GraphQL endpoint; err={str(e)}')
                continue

            if res.code != 200:
                await asyncio.sleep(0.5)
                logger.debug(f'Retrying GraphQL endpoint; status: {res.code}; '
                             f'error: {res.error}')
                res = None

        return res
