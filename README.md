# BiQuAD

## prerequisites

The data can be used as is, for generation (or use on custom datasets) Python >= 3.7 is required. The bundeled datalog interpreter used for answer retrieval requires node.js >= v15.5.

### create a virtual environment and install required Python packages

```py
# create environment
python3 -m venv .venv

# activate environment
source .venv/bin/activate

# install dependencies
pip install -r requirements.txt
```

### Install node.js dependencies

```bash
cd dltools/nodeinterp/
npm install .
```

### download ESDB

The `sqlite` database can be obtained via [Kaggle](https://www.kaggle.com/hugomathien/soccer/data). It should be placed in the `data` directory as `database.sqlite`.

## scripts

- `output_rulecount.py` Makes sure the transformations in `data/transformations` can be loaded properly.
- `kbtransform.py` Contains most of the transformation logic and can be invoked directly to syntax check the rulesets. The syntax check also outputs all placeholders or "fillers" defined per ruleset.
- `execdatalog.py` Runs the datalog interpreter for answer retrieval, can be directly invoked to test communication.
- `soccerdb.py` Contains the data model and SQL queries for matches, players, and events. Can be invoked directly to show the event dump of a random match in the database.
- `write_textrep.py` Applies textual representations to matches and events, output is written to `data/generated/reports/`
- `write_datalog.py` Similar to the above, generates datalog representations.
- `write_questions.py` Generates questions in textual and datalog form, the datalog query is then tested against the knowledge base. Output is written to `data/generated/questions`.
- `generate_unanswerable.py` Generates adverserial unanswerable questions in addition to those in `data/generated/questions`, output is saved to `data/generated/questionsfull`.
- `export_squad.py` Generates a new squad-like 60-20-20 split from the generated content.

## other data

- `data/generated-content/` The fully generated train/dev/test splits.
- `data/transformations/` The rulesets for transformations of match reports and questions into text and datalog.
