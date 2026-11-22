# Virtue Healthcare

Datathon project for cleaning India healthcare facility and postal data, tracking source-backed corrections, and building a facility search application.

## Repository layout

| Path | Contents |
| --- | --- |
| `agents/` | NABH verification and hospital-search intent agents; see [setup and tests](agents/README.md) |
| `app/` | Application workspace and data loading notes |
| `pipeline/` | Python cleaning pipeline and source-backed correction rules |
| `data/processed/` | Cleaned facility and postal snapshots, plus a one-row-per-PIN lookup |
| `data/evidence/` | Backfills, reviewed service claims, review queue, and QA summary |

The current snapshot contains **9,989 hospital records**, **165,625 post office records**, and **19,586 unique PINs**. It records **111 source-backed hospital field updates** and **28 remaining PIN–state conflicts**. See the [cleaning log](data/evidence/CLEANING_LOG.md) for the latest geography review and the [app data notes](app/README.md) for field semantics.

## Rebuild locally

The pipeline uses the Python standard library. Put your original v2 input files in the local `inputs/` folder and run this from the repository root:

```bash
python3 pipeline/run_clean.py --zip inputs/Datathon.zip --postal inputs/pincodes.csv --out build
```

The included snapshots can be read directly from `data/processed/`. Use the files generated in `build/` to check a new run before updating a snapshot.

## Source attribution

- Facility data came from the Virtue Foundation dataset for the Databricks Apps & Agents for Good Hackathon. Refer to the original listing for terms applicable to that data. [Datathon dataset description](https://dais-for-good-2026.devpost.com/resources)
- The postal reference is sourced from India Post through the Open Government Data Platform India and uses the Government Open Data License – India. [India Post source](https://data.gov.in/resource/all-india-pincode-directory-till-last-month) · [License](https://data.gov.in/Godl)
- The decision files name the hospital, accreditation, or government sources supporting individual changes. Geographic screening drew on geoBoundaries and map data © OpenStreetMap contributors. [geoBoundaries](https://www.geoboundaries.org/) · [OpenStreetMap copyright](https://www.openstreetmap.org/copyright)
