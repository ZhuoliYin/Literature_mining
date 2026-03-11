# Auto Literature Review - Paper Collector

Collect paper metadata (title, abstract, authors, links) from AI conferences.
Also supports querying Elsevier papers via official APIs.

## What this supports now

- [x] ICLR (via OpenReview)
- [ ] ICML (OpenReview first, then PMLR fallback)
- [ ] NeurIPS (OpenReview first, then NeurIPS proceedings fallback)
- [ ] AAAI (AAAI proceedings OJS)
- [ ] ACL (ACL Anthology)
- [ ] IJCAI (IJCAI proceedings)

## Setup

Make sure cd to the right directory
```bash

cd ./Auto-Literature-Review
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
  
python src/collect_papers.py \
--conference ICLR \
--year 2015 \
--format csv \
--output data/iclr_2015.csv \
--no-progress

```


Or Download in batch

```bash
mkdir -p data/iclr
for year in $(seq 2015 2026); do
  python src/collect_papers.py \
    --conference ICLR \
    --year "$year" \
    --format csv \
    --output "data/iclr/iclr_${year}.csv" \
    --no-progress \
done
```

## Output fields

- `conference`
- `year`
- `title`
- `abstract`
- `authors`
- `paper_url`
- `pdf_url`
- `source`

### ASReview Lab for human-AI collaborated systematic review

https://asreview.nl/install/

Create a clean environment to run ASReview Lab

```bash
conda create -n asreview_clean python=3.10 -y
conda activate asreview_clean
python -m pip install --upgrade pip setuptools wheel
python -m pip install asreview
python -m asreview lab
```