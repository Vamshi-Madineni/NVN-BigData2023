import * as Icon from 'react-feather';
import React, {useEffect, useMemo, useState} from 'react';
import Modal from '@material-ui/core/Modal';
import Typography from '@material-ui/core/Typography';
import './ModelStyles.css';
import axios from 'axios';
import {Loading} from '../visus/Loading/Loading';
import Papa from 'papaparse';
import Table from '@material-ui/core/Table';
import TableBody from '@material-ui/core/TableBody';
import TableCell from '@material-ui/core/TableCell';
import TableHead from '@material-ui/core/TableHead';
import TableRow from '@material-ui/core/TableRow';
import {ButtonGroup, Tooltip} from '@material-ui/core';
const baseurl = 'http://localhost:8002';

interface QueryStructure {
  data: Array<string>;
  error: boolean;
  message: string;
  dtypes: Array<string>;
}

const SqlModel: React.FC<{id: string}> = ({id}) => {
  const [show, setshow] = useState<boolean>(false);
  const [query_results, setQueryResults] = useState<QueryStructure>({
    data: [],
    error: false,
    message: '',
    dtypes: [],
  });
  const [loading, setloading] = useState(false);

  const fetchData = (query: string) => {
    setloading(true);
    // Create an axios instance with the required headers
    const instance = axios.create({
      headers: {
        'Access-Control-Allow-Origin': 'http://localhost:8001',
        'Access-Control-Allow-Headers': 'x-requested-with',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Credentials': 'true',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': 'macOS',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site',
      },
    });
    const data = {
      datasetId: id,
      query: query,
    };
    const hardcode =
      '{"results": {"schema": {"fields": [{"name": "index", "type": "integer"}, {"name": "County", "type": "string"}, {"name": "Year", "type": "integer"}, {"name": "Data_Type", "type": "string"}, {"name": "Mode", "type": "string"}, {"name": "Share", "type": "number"}, {"name": "Source", "type": "string"}], "primaryKey": ["index"], "pandas_version": "0.20.0"}, "data": [{"index": 0, "County": "Alameda County", "Year": 1960, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.749, "Source": "BayAreaCensus"}, {"index": 1, "County": "Alameda County", "Year": 1970, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.783, "Source": "BayAreaCensus"}, {"index": 2, "County": "Alameda County", "Year": 1980, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.776, "Source": "NHGIS_Census"}, {"index": 3, "County": "Alameda County", "Year": 1990, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.795, "Source": "NHGIS_Census"}, {"index": 4, "County": "Alameda County", "Year": 2000, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.802, "Source": "NHGIS_Census"}, {"index": 5, "County": "Alameda County", "Year": 2006, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.768, "Source": "B08301_ACS06_1YR"}, {"index": 6, "County": "Alameda County", "Year": 2007, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.774, "Source": "B08301_ACS07_1YR"}, {"index": 7, "County": "Alameda County", "Year": 2008, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.767, "Source": "B08301_ACS08_1YR"}, {"index": 8, "County": "Alameda County", "Year": 2009, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.764, "Source": "B08301_ACS09_1YR"}, {"index": 9, "County": "Alameda County", "Year": 2010, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.777, "Source": "B08301_ACS10_1YR"}]}}';
    // axios
    instance
      .post(baseurl + '/api/v1/queryduck', data)
      .then(res => {
        setQueryResults({
          data: JSON.parse(hardcode).results.data,
          error: false,
          message: '',
          dtypes: JSON.parse(hardcode).results.schema.fields.map(
            (field: any) => field.type
          ),
        });
      })
      .then(() => {
        console.log('Query Results:', query_results.data);
        setloading(false);
      });
  };

  const resetDataset = () => {
    setloading(true);
    axios
      .get(baseurl + '/reset?id=' + id)
      .then(res => {
        setQueryResults({
          data: JSON.parse(res.data.data),
          error: res.data.error,
          message: res.data.message,
          dtypes: res.data.dtypes,
        });
      })
      .then(() => setloading(false));
  };

  useEffect(() => {
    console.log('query results updated to');
    console.log(query_results);
  }, [query_results]);

  const toggleModel = () => {
    setshow(prev => !prev);
  };

  return (
    <>
      <button
        className="btn btn-sm btn-outline-primary"
        onClick={() => {
          fetchData('');
          toggleModel();
        }}
      >
        <Icon.Edit className="feather" /> Execute SQL
      </button>
      <PopupModel
        show={show}
        toggleModel={toggleModel}
        loading={loading}
        query_results={query_results}
        fetchData={fetchData}
        resetDataset={resetDataset}
      />
    </>
  );
};
interface ModelProps {
  show: boolean;
  loading: boolean;
  query_results: QueryStructure;
  toggleModel: () => void;
  fetchData: (query: string) => void;
  resetDataset: () => void;
}
interface HelpModelProps {
  showHelp: boolean;
  toggleHelp: () => void;
}

const HelpModel: React.FC<HelpModelProps> = ({showHelp, toggleHelp}) => {
  return (
    <Modal open={showHelp} onClose={toggleHelp}>
      <div className="help-div">
        <div style={{display: 'flex'}}>
          <Typography id="modal-modal-title" variant="h6" component="h2">
            Help Section
          </Typography>
          <div className="close-btn" style={{marginLeft: 'auto'}}>
            <Icon.X className="feather" onClick={toggleHelp} />
          </div>
        </div>

        <div className="help-body">
          <div>
            <span>
              The backend uses DuckDB to query the datasets. Use the keyword{' '}
              <span className="code-embeding">{'"DATASET"'}</span> to refer the
              table so that, in the Backend, the keyword{' '}
              <span className="code-embeding">{'"DATASET"'}</span> is replaced
              by the specific dataset ID.
              <br />
              Always use double quotes{' '}
              <span className="code-embeding">{'"Column Name"'}</span> while
              refering columns with spaces in their names
            </span>

            <div className="section">
              <span>Some example queries</span>
              <small className="embeded-sql"> SELECT * FROM DATASET</small>
              <small className="embeded-sql">
                DESCRIBE SELECT * FROM DATASET
              </small>
              <small className="embeded-sql">
                {' '}
                SELECT {'{column-name}'}, count(*) FROM DATASET GROUP BY
                {'{column-name}'}
              </small>

              <small className="embeded-sql">
                {' '}
                ALTER TABLE DATASET ALTER {'{column-name}'} TYPE {'{data-type}'}
                ;
              </small>
            </div>
            <div className="section">
              <span>Common Data types in DuckDB</span>
              <ul>
                <li>BIGINT</li>
                <li>TIMESTAMP</li>
                <li>VARCHAR</li>
                <li>FLOAT</li>
                <li>DOUBLE</li>
                <li>
                  <a
                    href="https://duckdb.org/docs/sql/data_types/overview.html"
                    target="_blank"
                    rel="noreferrer"
                  >
                    More...
                  </a>{' '}
                </li>
              </ul>
            </div>
            <div className="section">
              <span>Features</span>
              <ul>
                <li>
                  Users can write custom SQL Queries to transform dataset or
                  select only the required data that you want
                </li>
                <li>
                  Users can change the data types of columns based on their
                  requirements
                </li>
                <li>Users can download the result of their SQL queries</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
};

const PopupModel: React.FC<ModelProps> = ({
  show,
  loading,
  query_results,
  toggleModel,
  fetchData,
  resetDataset,
}) => {
  const [sqlQuery, setsqlQuery] = useState<string>('select * from DATASET;');
  const [showHelp, setshowHelp] = useState<boolean>(false);

  const toggleHelp = () => {
    setshowHelp(prev => !prev);
  };

  useEffect(() => {
    setsqlQuery('select * from DATASET;');
  }, [show]);

  const reset_dataset = () => {
    resetDataset();
    setsqlQuery('select * from DATASET;');
  };
  // const hardcodejson =
  //     {"results": {"schema": {"fields": [{"name": "index", "type": "integer"}, {"name": "County", "type": "string"}, {"name": "Year", "type": "integer"}, {"name": "Data_Type", "type": "string"}, {"name": "Mode", "type": "string"}, {"name": "Share", "type": "number"}, {"name": "Source", "type": "string"}], "primaryKey": ["index"], "pandas_version": "0.20.0"}, "data": [{"index": 0, "County": "Alameda County", "Year": 1960, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.749, "Source": "BayAreaCensus"}, {"index": 1, "County": "Alameda County", "Year": 1970, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.783, "Source": "BayAreaCensus"}, {"index": 2, "County": "Alameda County", "Year": 1980, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.776, "Source": "NHGIS_Census"}, {"index": 3, "County": "Alameda County", "Year": 1990, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.795, "Source": "NHGIS_Census"}, {"index": 4, "County": "Alameda County", "Year": 2000, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.802, "Source": "NHGIS_Census"}, {"index": 5, "County": "Alameda County", "Year": 2006, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.768, "Source": "B08301_ACS06_1YR"}, {"index": 6, "County": "Alameda County", "Year": 2007, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.774, "Source": "B08301_ACS07_1YR"}, {"index": 7, "County": "Alameda County", "Year": 2008, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.767, "Source": "B08301_ACS08_1YR"}, {"index": 8, "County": "Alameda County", "Year": 2009, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.764, "Source": "B08301_ACS09_1YR"}, {"index": 9, "County": "Alameda County", "Year": 2010, "Data_Type": "Residence", "Mode": "All Auto", "Share": 0.777, "Source": "B08301_ACS10_1YR"}]}};
  // const [query_result, setQueryResults] = useState<QueryStructure>({
  //   data: hardcodejson.results.data,
  //   error: false,
  //   message: '',
  //   dtypes: hardcodejson.results.schema.fields.map(
  //     (field: any) => field.type
  //   ),
  // });
  // const TableComponent = useMemo(() => {
  //   if (query_result && query_result.data.length) {
  //     return (
  //       <div className="results-div">
  //         <Table style={{width: '100%'}}>
  //           <TableHead style={{width: '100%', position: 'sticky', top: '0'}}>
  //             <TableRow style={{backgroundColor: '#63508b'}}>
  //               {Object.keys(query_results.data[0]).map((col, id) => (
  //                 <TableCell key={id} style={{color: 'white'}}>
  //                   {col}
  //                   <div>
  //                     <span className="badge badge-pill semtype semtype-enumeration">
  //                       {query_result.dtypes[id]}
  //                     </span>
  //                   </div>
  //                 </TableCell>
  //               ))}
  //             </TableRow>
  //           </TableHead>
  //           <TableBody>
  //             {query_results.data.map((row, id) => (
  //               <TableRow key={id} className="table-row">
  //                 {Object.values(row).map((val, id) => (
  //                   <TableCell key={id}>
  //                     {typeof val === 'string' ? val.substring(0, 150) : val}
  //                   </TableCell>
  //                 ))}
  //               </TableRow>
  //             ))}
  //           </TableBody>
  //         </Table>
  //       </div>
  //     );
  //   }
  //   return <div></div>;
  // }, [query_results]);
  function downloadCsvData() {
    const csvData = Papa.unparse(query_results.data);
    const dataStr =
      'data:text/csv;charset=utf-8,' + encodeURIComponent(csvData);
    const link = document.createElement('a');
    link.setAttribute('href', dataStr);
    link.setAttribute('download', 'Modified.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }
  return (
    <Modal open={show} onClose={toggleModel}>
      <div className="modal-div ">
        <div style={{display: 'flex', marginBottom: '10px'}}>
          <Typography id="modal-modal-title" variant="h6" component="h2">
            Execute SQL Query
          </Typography>
          <div className="close-btn" style={{marginLeft: 'auto'}}>
            <Icon.X className="feather" onClick={toggleModel} />
          </div>
        </div>
        <div className="toolbar">
          <span>Editor</span>
          <div className="tool-btns">
            <div className="right-btns">
              {/* <Tooltip
                title="How to use"
                placement="top"
                arrow
                onClick={toggleHelp}
              >
                <button className="btn btn-sm btn-outline-primary">
                  <div className="icon-holder">
                    <Icon.HelpCircle className="feather" /> Help
                  </div>
                </button>
              </Tooltip> */}

              <Tooltip
                title="Download the queried dataset"
                placement="top"
                arrow
                onClick={downloadCsvData}
              >
                <button className="btn btn-sm btn-outline-primary">
                  <div className="icon-holder">
                    <Icon.Download className="feather" /> Download
                  </div>
                </button>
              </Tooltip>
              {/* <Tooltip
                title="Reset the table"
                placement="top"
                arrow
                onClick={reset_dataset}
              >
                <button className="btn btn-sm btn-outline-primary">
                  <div className="icon-holder">
                    <Icon.RefreshCw className="feather" /> Reset
                  </div>
                </button>
              </Tooltip> */}
              <Tooltip
                title="Clear the query"
                placement="top"
                arrow
                onClick={() => setsqlQuery('')}
              >
                <button className="btn btn-sm btn-outline-primary">
                  <div className="icon-holder">
                    <Icon.XOctagon className="feather" /> Erase Query
                  </div>
                </button>
              </Tooltip>
              {/* <Tooltip
                title="Change column data types"
                placement="top"
                arrow
                onClick={() =>
                  setsqlQuery(
                    'ALTER TABLE DATASET ALTER {column name} TYPE {data type};'
                  )
                }
              >
                <button className="btn btn-sm btn-outline-primary">
                  <div className="icon-holder">
                    <Icon.Edit className="feather" /> Edit
                  </div>
                </button>
              </Tooltip> */}
              <Tooltip title="Run query" placement="top" arrow>
                <div
                  className="run-query-btn"
                  onClick={() => fetchData(sqlQuery)}
                >
                  Run
                </div>
              </Tooltip>
            </div>
          </div>
        </div>

        <div className="query-div">
          <textarea
            placeholder="Write Query"
            value={sqlQuery}
            onChange={e => setsqlQuery(e.target.value)}
            rows={5}
          />
          {!loading && query_results.data && (
            <span>Total {query_results.data.length} Rows Fetched</span>
          )}
        </div>
        {!loading &&
          !query_results.error &&
          query_results.data.length &&
          TableComponent}
        {query_results.error && !loading && <div>{query_results.message}</div>}
        {loading && (
          <div className="loading-div">
            <Loading message="Loading..." />
          </div>
        )}
        <HelpModel showHelp={showHelp} toggleHelp={toggleHelp} />
      </div>
    </Modal>
  );
};

export default SqlModel;
