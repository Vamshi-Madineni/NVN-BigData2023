function(
  config,
  cache_size,
  local_cache_path,
) (
  [
    {
      apiVersion: 'v1',
      kind: 'PersistentVolume',
      metadata: {
        name: 'cache',
        labels: {
          type: 'local',
          app: 'auctus',
          what: 'cache',
        },
      },
      spec: {
        storageClassName: 'manual',
        capacity: {
          storage: cache_size,
        },
        accessModes: [
          'ReadWriteMany',
        ],
        'local': {
          path: local_cache_path,
        },
        nodeAffinity: {
          required: {
            nodeSelectorTerms: (
              // Match the local_cache_node_label if set
              if config.local_cache_node_label != null then [
                {
                  matchExpressions: [
                    {
                      key: config.local_cache_node_label,
                      operator: 'Exists',
                    },
                  ],
                },
              ]
              else []
            ),
          },
        },
      },
    },
    {
      apiVersion: 'v1',
      kind: 'PersistentVolumeClaim',
      metadata: {
        name: 'cache',
      },
      spec: {
        storageClassName: 'manual',
        volumeName: 'cache',
        accessModes: [
          'ReadWriteMany',
        ],
        resources: {
          requests: {
            storage: cache_size,
          },
        },
      },
    },
    {
      apiVersion: 'v1',
      kind: 'PersistentVolumeClaim',
      metadata: {
        name: 'geo-data',
      },
      spec: {
        accessModes: [
          'ReadOnlyMany',
          'ReadWriteOnce',
        ],
        resources: {
          requests: {
            storage: '2.5Gi',
          },
        },
      },
    },
    {
      apiVersion: 'v1',
      kind: 'PersistentVolumeClaim',
      metadata: {
        name: 'es-synonyms',
      },
      spec: {
        accessModes: [
          'ReadOnlyMany',
          'ReadWriteOnce',
        ],
        resources: {
          requests: {
            storage: '5Mi',
          },
        },
      },
    },
  ]
)
