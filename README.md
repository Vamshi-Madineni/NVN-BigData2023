Auctus
======

This project is a web crawler and search engine for datasets, specifically meant for data augmentation tasks in machine learning. It is able to find datasets in different repositories and index them for later retrieval.

Requirements:

Docker should be installed and started.

Python should be installed


[Documentation is available here](https://docs.auctus.vida-nyu.org/)

[Documention of modified architecture and implemented features](https://github.com/Vamshi-Madineni/NVN-BigData2023/blob/master/NVN_BigData_FInal_Report.pdf)

It is divided in multiple components:

* Libraries
  * [Geospatial database](https://gitlab.com/ViDA-NYU/auctus/datamart-geo) `datamart_geo`. This contains data about administrative areas extracted from Wikidata and OpenStreetMap. It lives in its own repository and is used here as a submodule.
  * [Profiling library](lib_profiler/) `datamart_profiler`. This can be installed by clients, will allow the client library to profile datasets locally instead of sending them to the server. It is also used by the apiserver and profiler services.
  * [Materialization library](lib_materialize/) `datamart_materialize`. This is used to materialize dataset from the various sources that Auctus supports. It can be installed by clients, which will allow them to materialize datasets locally instead of using the server as a proxy.
  * [Data augmentation library](lib_augmentation/) `datamart_augmentation`. This performs the join or union of two datasets and is used by the apiserver service, but could conceivably be used stand-alone.
  * [Core server library](lib_core/) `datamart_core`. This contains common code for services. Only used for the server components. The [filesystem locking](lib_fslock/) code is separate as `datamart_fslock` for performance reasons (has to import fast).
* Services
  * [**Discovery services**](discovery/): those are responsible for discovering datasets. Each plugin can talk to a specific repository. *Materialization metadata* is recorded for each dataset, to allow future retrieval of that dataset.
  * [**Profiler**](profiler/): this service downloads a discovered dataset and computes additional metadata that can be used for search (for example, dimensions, semantic types, value distributions). Uses the profiling and materialization libraries.
  * **Lazo Server**: this service is responsible for indexing textual and categorical attributes using [Lazo](https://github.com/mitdbg/lazo). The code for the server and client is available [here](https://gitlab.com/ViDA-NYU/auctus/lazo-index-service).
  * [**apiserver**](apiserver/): this service responds to requests from clients to search for datasets in the index (triggering on-demand query by discovery services that support it), upload new datasets, profile datasets, or perform augmentation. Uses the profiling and materialization libraries. Implements a JSON API using the Tornado web framework.
  * [The **cache-cleaner**](cache_cleaner/): this service makes sure the dataset cache stays under a given size limit by removing least-recently-used datasets when the configured size is reached.
  * [The **coordinator**](coordinator/): this service collects some metrics and offers a maintenance interface for the system administrator.
  * [The **frontend**](frontend/): this is a React app implementing a user-friendly web interface on top of the API.

![Modified Auctus Architecture](docs/modarch.png)

Elasticsearch is used as the search index, storing one document per known dataset.

The services exchange messages through `RabbitMQ`, allowing us to have complex messaging patterns with queueing and retrying semantics, and complex patterns such as the on-demand querying.



Deployment
==========

The system is currently running at https://auctus.vida-nyu.org/. You can see the system status at https://grafana.auctus.vida-nyu.org/.

Local deployment / development setup
====================================

To deploy the system locally using docker-compose, follow those step:

Set up environment
------------------

Make sure you have checked out the submodule with `git submodule init && git submodule update`

Make sure you have [Git LFS](https://git-lfs.github.com/) installed and configured (`git lfs install`)

Copy env.default to .env and update the variables there. You might want to update the password for a production deployment.

Make sure your node is set up for running Elasticsearch. You will probably have to [raise the mmap limit](https://www.elastic.co/guide/en/elasticsearch/reference/7.6/vm-max-map-count.html).

The `API_URL` is the URL at which the apiserver containers will be visible to clients. In a production deployment, this is probably a public-facing HTTPS URL. It can be the same URL that the "coordinator" component will be served at if using a reverse proxy (see [nginx.conf](nginx.conf)).

To run scripts locally, you can load the environment variables into your shell by running: `. scripts/load_env.sh` (that's *dot space scripts...*)

Prepare data volumes
--------------------

Run `scripts/setup.sh` to initialize the data volumes. This will set the correct permissions on the `volumes/` subdirectories.

Should you ever want to start from scratch, you can delete `volumes/` but make sure to run `scripts/setup.sh` again afterwards to set permissions.

Build the containers
--------------------

```
$ docker-compose build --build-arg version=$(git describe) apiserver
```

Start the base containers
-------------------------

```
$ docker-compose up -d elasticsearch rabbitmq redis minio lazo
```

These will take a few seconds to get up and running. Then you can start the other components:

```
$ docker-compose up -d cache-cleaner coordinator profiler apiserver apilb frontend
```

You can use the `--scale` option to start more profiler or apiserver containers, for example:

```
$ docker-compose up -d --scale profiler=4 --scale apiserver=8 cache-cleaner coordinator profiler apiserver apilb frontend
```


### Reproducibility:

Git clone the above project.

Follow the above steps to host the docker environment

Then run the following commands
```
pip3 install flask 
pip3 install flask_cors 
pip3 install duckdb
pip3 install minio 
pip3 install pandas 
pip3 install pyarrow  
```

Then goto auctus location and run following command to start the Flask APP
```
python3 main.py

```

Import a snapshot of our index
-----------------------------------------

```
$ scripts/docker_import_snapshot.sh
```

This will download an Elasticsearch dump from auctus.vida-nyu.org and import it into your local Elasticsearch container.

Now go the auctus link http://localhost:8001

Search for term like 'cities'.

From the search result you can see the button "Execute SQL"

First click on "Copy ID"

![Copy](docs/copy.png)

Now click on "Execute SQL", it would redirect to new tab.

Now paste the datasetId on Dataset ID field

Run this command on the sql section.

"SELECT * FROM data LIMIT 10;"

You can also download the queried data using "Download as CSV" button.

![data](docs/data.png)


It is possible to modify the limit and select columns, while maintaining the table name as "data". The dataset is being manipulated in the backend, but for ease of use for the user, we have chosen to temporarily name the table "data".



## Reproducibility for parsing Parquet in the Profiling pipeline

We have modified Profiling pipeline to handle parquet file along with csv.
To test the above pipeline execute the below commands where we are creating a sample parquet file and loading into the profiling pipeline using the profiler library process_dataset function
Go to profiler container on docker desktop.
Now click on Terminal.
```
$ cd  
$ ls
$ python3
Python 3.8.16 (default, May  4 2023, 06:20:30) 
[GCC 10.2.1 20210110] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> import datamart_profiler
>>> import pandas
>>> df = pandas.DataFrame({
...     'place': ['france', 'france', 'italy', 'germany'],
...     'favorite': ['Brittany', 'Normandie', 'Hamburg', 'Bavaria'],
... })
>>> df.to_parquet("sample.parquet")
>>> datamart_profiler.process_dataset("sample.parquet")
{'nb_rows': 4, 'nb_profiled_rows': 4, 'nb_columns': 2, 'columns': [{'name': 'place', 'structural_type': 'http://schema.org/Text', 'semantic_types': [], 'num_distinct_values': 3}, {'name': 'favorite', 'structural_type': 'http://schema.org/Text', 'semantic_types': [], 'num_distinct_values': 4}], 'types': [], 'attribute_keywords': ['place', 'favorite']}
>>> 


```

![Steps for the above](docs/step1.png)
![Steps for the above](docs/step2.png)
![Steps for the above](docs/step3.png)


### Minio Creds
username: devkey
pass : devpassword


Ports:
* The web interface is at http://localhost:8001
* Flask is at http://localhost:5001
* Api for executing SQL query http://localhost:5001/query
* The API at http://localhost:8002/api/v1 (behind HAProxy)
* Elasticsearch is at http://localhost:8020
* The Lazo server is at http://localhost:8030
* The RabbitMQ management interface is at http://localhost:8010
* The RabbitMQ metrics are at http://localhost:8012
* The Minio interface is at http://localhost:8050 (if you use that)
* The HAProxy statistics are at http://localhost:8004
* Prometheus is at http://localhost:8040
* Grafana is at http://localhost:8041





Prometheus is configured to automatically find the containers (see [prometheus.yml](docker/prometheus.yml))
