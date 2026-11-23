# Pells

Bank and card statements in. A ledger checked against the printed balances, and a numbered set of pages for the other side, out.

The name: the Clerk of the Pells entered the Exchequer's receipts and payments on rolls of parchment, the pells.

It runs on your Mac with Python 3.9 and two Python packages. `pells desk` serves a page on 127.0.0.1; the other commands make no network calls.

The example matter, *Jane Doe v. Roe Holdings, LLC*, is fictional. So are its bank, accounts, vendors and people. The window, showing that matter: https://nanobotco.github.io/pells/

## What it does

1. **Reads the page, not the file name.** A download from a bank portal is often a bundle: two accounts in one file, the same statement twice, a month absent. Each line is filed under the account and period printed on its own page.
2. **Checks the arithmetic.** For each statement: opening balance plus the lines, compared with the closing balance printed on it. The index says `reconciled`, or `off by $488.14`, which points at an absent page or a misread line.
3. **Lists what it did not read.** Scans with no text layer, files that are copies of another, and pages that carry amounts but match no layout.
4. **Sorts lines into piles.** A pile is a word match (utilities, building trades, cash, checks): a reason to read a line. Lines that match no pile get their own pile.
5. **Carries your marks.** You mark lines `y`, `n` or `?` in `marks.csv` or in the window. A rebuild carries the marks over by line id.
6. **Makes the production.** The pages that carry a marked line are stamped with a Bates number (a prefix and a running number, one per page, the usual way pages are numbered when documents are handed to the other side in a lawsuit), with an index that ties each number to its source file and page, and SHA-256 hashes of source and output.
7. **Pairs receipts.** Reads each receipt's date and total and pairs it with the ledger line for the same amount, 3 days before to 10 days after.
8. **Searches chats.** Finds the threads in a Messenger download or a text export that carry the subject words, and sorts them into tiers for reading.
9. **Writes a search log.** One entry for each thing read, with its counts, whether or not anything turned up.

Pages are stamped as they are in the source. Pells does not redact.

## Install

```sh
cd pells
python3 -m pip install --user -r requirements.txt     # pypdf, reportlab
bin/pells --help
```

`INSTALL.txt` has the same steps in plain words, and `Pells.command` opens the window with a double-click.

## Try it on the example

```sh
python3 scripts/make_example.py                 # writes examples/doe-v-roe
bin/pells read examples/doe-v-roe/statements
bin/pells piles
bin/pells mark --yes --pile "building trades"
bin/pells produce --prefix DOE --first-page
bin/pells receipts examples/doe-v-roe/receipts
bin/pells chats examples/doe-v-roe/chats
bin/pells log
```

Or `bin/pells desk`, then **Try the example**.

## Commands

| Command | What it does |
|---|---|
| `read <folder>` | Statement PDFs to `ledger.json`, `ledger.csv` and `index.txt` |
| `piles [--rules FILE]` | `piles.txt` and the marks sheet `marks.csv` |
| `mark <id>... --yes\|--no\|--ask [--pile WORDS] [--note TEXT]` | Marks lines, or a whole pile |
| `produce --prefix DOE [--start N] [--unit page\|statement] [--first-page] [--replace]` | Numbered PDFs, `production-index.txt` and `.csv` |
| `receipts <folder> [--days-before 3] [--days-after 10]` | `receipts.csv`, `receipts.txt` |
| `chats <folder> [--terms FILE]` | `chats.csv`, `chats.txt`, staged threads in `chats-staged/` |
| `log` | Prints the search log |
| `layouts` | Lists the statement layouts |
| `ocr file.pdf...` | Puts a text layer on scans (needs ocrmypdf) |
| `desk [--port 8780]` | Large-type window in the browser, English and Thai |

Each command takes `--work DIR` (default `./pells-work`). Everything Pells writes goes there.

## Layouts

A layout is one JSON file in `layouts/`: a phrase that spots the bank's pages, patterns for the account, the period and the balances, and how one transaction is laid out.

| Layout | Style | Checked against |
|---|---|---|
| `usaa-deposit` | a transaction opens at MM/DD and runs to the next | 128 statements: 118 reconcile, 10 are short of pages or balances |
| `usaa-card` | one field per line | 67 statements; no balance check yet |
| `plain-running-balance` | one line per transaction with a running balance | the example matter |

To add a bank, copy `plain-running-balance.json`, change `detect` to a phrase printed on that bank's pages, and adjust the patterns. A work folder's own `layouts/` folder is read too. The approach (a rule table per bank, totals checked against the opening and closing balance) is the one the open-source statement parsers `transtractor` and `monopoly` use; no code of theirs is in Pells.

## Tests

```sh
python3 tests/run.py
```

## Licence

Code: MIT. Text: CC BY 4.0. See `LICENSE` and `NOTICE.txt`.
