const datascript_mori = require('datascript-mori');
const fs = require("fs").promises;

const mori = datascript_mori.mori;
const djs = datascript_mori.datascript.js;
const dcljs = datascript_mori.datascript.core;
const helpers = datascript_mori.helpers;
const {hashMap, vector, parse, toJs, equals, isMap, hasKey, isSet, set, getIn, get} = mori
const {DB_VALUE_TYPE, DB_TYPE_REF, DB_ADD, DB_ID, TEMPIDS} = helpers

let DEBUG = false;
if (process.env.DEBUG !== undefined) {
    if (process.env.DEBUG == 'true' || process.env.DEBUG == '1') {
        DEBUG = true;
    }
}

function dl_test() {
    const schema = {"aka": {":db/cardinality": ":db.cardinality/many"}, "friend": {":db/valueType": ":db.type/ref"}, "name": {":db/type": "db.type/string"}};

    let conn = djs.create_conn(schema);

    djs.listen(conn, "main", () => {
        console.error("connection/main");
    });

    djs.transact(conn, [
         {
          ":db/id": -1,
          "name": "Ivan",
          "age": 18,
          "aka": ["X", "Y"]
        },
        {
          ":db/id": -2,
          "name": "Igor",
          "aka": ["Grigory", "Egor"]
        },
        [":db/add", -1, "friend", -2]
    ]);

    var result = dcljs.q(parse('[:find ?n :in $ ?a :where [?e "friend" ?f] [?e "age" ?a] [?f "name" ?n]]'), djs.db(conn), 18);
    console.error(result);
    console.error("isSet(result)", isSet(result));
    console.error("eq", equals(result, set([vector("Igor")])) );

    conn = djs.create_conn();
    djs.transact(conn, [
      [':db/add', 1, 'weight', 200]
    ]);
    djs.transact(conn, [
      [':db.fn/cas', 1, 'weight', 200, 300]
    ]);
    var e = djs.entity(djs.db(conn), 1);
    console.error("applied", e.get('weight') === 300);
}

async function readStdin() {
    return new Promise(function(resolve, reject) {
        let buf = "";
        process.stdin.on("data", data => {
            buf += data.toString();
        });
        process.stdin.on("end", () => {
            return resolve(buf.trim());
        });
    });
}

const DL_COMMENT = ";; ";
const DL_SECTION = ";;# ";

function splitSections(input_data) {
    input_data = input_data.split("\n");
    const result_data = {}
    const input_order = [];

    let cur_section = "data"; // default to data section

    for (let i = 0, l = input_data.length; i < l; i++) {
        let line = input_data[i];
        if (line.toLowerCase().trim().startsWith(DL_SECTION)) {
            line = line.toLowerCase().trim().substring(DL_SECTION.length);
            // console.error("SECTION -" + line + "-");
            cur_section = line;
            input_order.push(cur_section);
            continue;
        }

        //if (line.trim() === '' || line.trim().startsWith(DL_COMMENT)) {
        if (line.trim().startsWith(DL_COMMENT)) {
            continue;
        }

        if (!result_data.hasOwnProperty(cur_section)) {
            result_data[cur_section] = [];
        }

        result_data[cur_section].push(line);
    }

    for (const key of Object.keys(result_data)) {
      result_data[key] = result_data[key].join("\n").trim();
    }

    return [result_data, input_order];
}

var conn = null;

function translateSchema(parsed) {
    const translated = {}

    for (let i = 0, l = parsed.length; i < l; i++) {
        let entry = parsed[i];
        let ident = entry.ident;
        delete entry['ident'];
        translated[ident] = {};

        for (let [key, value] of Object.entries(entry)) {
            if (key === "valueType" && value === 'ref') {
                value = ":db.type/ref"; // lib only supports refs
            } else if (key === "valueType") {
                continue;
            }
            if (key === "cardinality") {
                value = ":db.cardinality/" + value;
            }
            translated[ident][":db/" + key] = value;
        }

        if (DEBUG) {
            console.error(i, entry, translated);
        }
    }

    return translated;
}

async function handle_schema(section) {
    console.error("handling schema");
    const parsed_section = parse(section);
    let parsed_section_obj = toJs(parsed_section);

    console.error("schema contains", parsed_section_obj.length, "descriptors");
    if (DEBUG) {
        console.error("----------------------------");
        console.error(section);
        console.error("----------------------------");
        console.error(parsed_section_obj);
        console.error("----------------------------");
        parsed_section_obj = translateSchema(parsed_section_obj);
        console.error(parsed_section_obj);
        console.error("----------------------------");
    }
    
    return parsed_section_obj
}

async function handle_data(section) {
    console.error("handling data");
    const parsed_section = parse(section);
    const parsed_section_obj = toJs(parsed_section);

    console.error("data contains", parsed_section_obj.length, "statements");
    if (DEBUG) {
        console.error("----------------------------");
        console.error(parsed_section_obj);
        console.error("----------------------------");
    }
    console.error("adding namespaces");
    const translated = [];
    let match_data = null;
    for (let i = 0, l = parsed_section_obj.length; i < l; i++) {
        const trobj = {};
        const entry = parsed_section_obj[i];
        let is_match = false;
        
        if (entry === undefined) { continue; }

        for (let [key, value] of Object.entries(entry)) {
            let namespace = ":event/";
            if (entry.score) {
                namespace = ":match/";
                is_match = true;
            }
            trobj[namespace + key] = value;
        }
        if (is_match) {
            match_data = trobj;
        } else {
        }
        translated.push(trobj);
    }
    if (DEBUG) {
        console.error("----------------------------");
        console.error(translated);
        console.error("----------------------------");
    }

    let obj_id = 1;
    console.error("inserting match");
    if (match_data) {
        match_data[DB_ID] = obj_id++;
    }
    // dcljs.transact(conn, [ match_data ]);
    let rels = [];
    for (let i = 0, l = translated.length; i < l; i++) {
        translated[i][DB_ID] = obj_id;
        if (match_data) {
            for (let [key, value] of Object.entries(match_data)) {
                if (key == DB_ID) continue;
                if (!translated[i].hasOwnProperty(key)) {
                    translated[i][key] = value;
                }
            }
        }
        obj_id++;
    }
    
    console.error("inserting events", translated.length);
    djs.transact(conn, translated);
    
    /* let asvectors = [];

    for (let i = 0, l = translated.length; i < l; i++) {
        const obj = translated[i];
        const objid = obj[DB_ID];
        delete obj[DB_ID];

        for (let [key, value] of Object.entries(obj)) {
            if (key === DB_ID) continue;
            let entry = [":db/add", objid, key, value];

            asvectors.push(entry);
        }
    }

    console.error("inserting events", asvectors.length, "vectors");
    console.error(asvectors);
    djs.transact(conn, asvectors); 
    */

    console.error("insertion complete");
}

var input_query = null;
var input_args = null;

async function handleInput(input_data, input_order) {
    let schema = null;

    for (const key of input_order) {
        const section = input_data[key];
        if (!section.length) { 
            console.error("section", key, "empty");
            continue;
        }

        if (key === "schema") {
            schema = await handle_schema(section);
        } else if (key === "data") {
            if (!conn) {
                if (!schema) {
                    conn = djs.create_conn({});
                    console.error("created connection w/o schema")
                } else {
                    conn = djs.create_conn(parsed_section_obj);
                    console.error("created connection w/ schema")
                }
                djs.listen(conn, "main", () => {
                    console.error("connection/main");
                });
            }
            await handle_data(section);
        } else if (key === "query") {
            input_query = section;
        } else if (key === "args" || key === 'arguments') {
            input_args = JSON.parse(section);
        } else {
            console.error("unknown section", key);
            process.exit(1);
        }
        console.error("==>", key);
    }
}

function queryDB(query, query_args) {
    const query_parsed = parse(query);
    const db_conn = djs.db(conn);

    const result = dcljs.q(query_parsed, db_conn, query_args);
    const result_obj = toJs(result);
    if (DEBUG) {
        console.error("query\n", query, "\nresult", result_obj);
    }
    return result_obj; 
}

(async function main() {
    const target = process.argv[2] || null;
    let input_data = null;

    if (!target) {
        console.error("missing CLI argument")
        process.exit(1);
    }
    if (target === '-') {
        // input from stdin
        console.error("reading input from STDIN");
        input_data = await readStdin();
    } else {
        console.error("reading from input file", target);
        let input = await fs.readFile(target);
        input_data = input.toString().trim();
    }

    if (!input_data) {
        console.error("no input data");
        process.exit(1);
    }

    const [split_input, input_order] = splitSections(input_data);
    
    try {
        console.error("starting to process input");
        await handleInput(split_input, input_order);
        console.error("input handling complete");
    } catch (err) {
        console.error("exception while handling input");
        console.error(err);
        process.exit(1);
    }
    
    if (input_query) {
        let queries = [];
        let do_split = true;
        let propagate = true;

        if (do_split) {
            const splitquery = input_query.split("\n");
            for (let i = 0, l = splitquery.length; i < l; i++) {
                const line = splitquery[i];
                if (line.trim().startsWith(";;")) {
                    continue;
                }

                if (line.indexOf(":find ") > -1) {
                    queries.push([]);
                }
                if (line.trim().length === 0) {
                    continue;
                }
                if (queries.length === 0) {
                    queries.push([]);
                }
                queries[queries.length - 1].push(line);
            }
            for (let i = 0, l = queries.length; i < l; i++) {
                queries[i] = queries[i].join("\n").trim();
            }
        } else {
            queries = [input_query];
        }

        console.error("starting to process", queries.length, "queries");
        let lastres = null;
        for (let i = 0, l = queries.length; i < l; i++) {
            if (!queries[i]) { continue; }
            try {
                console.error("QUERY", queries[i], "INPUT", input_args);
                console.error("IM_QUERY:" + JSON.stringify(queries[i]));
                console.error("IM_ARGS:" + JSON.stringify(input_args));
                const query_res = queryDB.apply(this, [queries[i]].concat(input_args));
                if (query_res && query_res.length) {
                    lastres = query_res;
                    console.error("IM_RESULT:" + JSON.stringify(query_res))
                }
                if (propagate && query_res.length) {
                    input_args = []
                    for (let qi = 0; qi < query_res[0].length; qi++) {
                        input_args.push( query_res[0][qi] );
                    }
                    // input_args = query_res[0][0];
                }
            } catch (err) {
                console.error("exception while querying");
                console.error(err);
                process.exit(1);
            }
        }
                
        if (lastres && lastres.length) {
            console.log(lastres[0]);
        }
            
        console.error("input handling complete");
    }
    
    //const query = '[:find ?e\n' + 
    //              ':where [?e :movie/title]]';
    /* dump test
    let query = '[:find ?id \n' +
        ':where [?id]]'
    let objids = queryDB(query, []);
    console.error("db content", objids);

    for (let i = 0, l = objids.length; i < l; i++) {
        const res = objids[i][0];
        console.error("-----", "#" + res); 
        query = '[:find ?id ?rel ?val \n' +
            ':in $ ?id \n' +
            ':where [?id ?rel ?val]] \n' 
        console.error(queryDB(query, res));
    }
    */

})();

