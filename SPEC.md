# Contact Cleaner — Spec

## Input
- A CSV file of contacts (like a spreadsheet saved as text)
- The first row is a header with the column names
- Columns: name, email, phone, company, city
- Each row after the header is one contact
- The data is messy: typed by different people, with extra spaces, inconsistent formats, duplicates, and missing values

## Cleaning rules
- Trim extra spaces from every value
- Treat "N/A", "null", "none", "-" and similar placeholders as empty
- Names: Title Case (john SMITH → John Smith). Known limitation: names like McDonald or O'Brien may not capitalize perfectly
- Emails: lowercase. A valid email has text, then @, then a domain with a dot (example: name@site.com)
- Invalid email → the whole row is rejected (see Rejected rows)
- Phones: convert to US format (713) 555-0123. Keep only the digits; accept 10 digits, or 11 digits starting with 1
- Phone that can't be converted (wrong number of digits) → leave the phone blank and note it in the report

## Duplicates
- Two rows are the same person if they have the same email OR the same phone number
- Compare AFTER cleaning (so JOHN@GMAIL.COM and john@gmail.com match)
- Ignore blank values when comparing (two rows with no phone are not duplicates because of that)
- Keep the most complete row (the one with the most filled-in fields)
- If two rows are equally complete, keep the first one
- List every removed duplicate in the report, next to the row that was kept

## Rejected rows
- Reject a row if ANY of these is true:
  - The email is invalid (it has a value, but not a valid format)
  - The name is missing
  - There is no email AND no phone (after cleaning; a phone that couldn't be converted counts as no phone)
- A blank email is NOT invalid: keep the row if it has a phone
- Order: clean every row first, then remove rejected rows, then remove duplicates
- Rejected rows go to contacts_rejected.csv with their ORIGINAL messy values, plus a "reason" column
- If a row has more than one problem, list all reasons (example: "missing name; invalid email")

## Outputs
- All outputs go in an output/ folder (create it if it doesn't exist)
- output/contacts_clean.csv: the clean, deduplicated contacts, same 5 columns
- output/contacts_rejected.csv: rejected rows with ORIGINAL values plus a "reason" column
- output/report.html: a professional report a client could read, with these sections:
  1. Summary: rows in, clean rows out, duplicates removed, rows rejected, phones blanked.
     The numbers must add up: rows in = clean rows + duplicates removed + rows rejected
  2. Changes: a before/after table showing ONLY rows that changed, with the changed values highlighted
  3. Duplicates: each removed row next to the row that was kept
  4. Rejected: each rejected row with its reason(s)
- Run it with: python cleaner.py <input file>  (example: python cleaner.py sample_messy.csv)

## Constraints
- Python 3.14, standard library only (csv, re, html, os). No pip installs
- One file: cleaner.py
- Must work on Windows
- Readable code over clever code: I'm a beginner and need to understand it
- A plain-English comment above every function explaining what it does
- Never modify the input file
- Never crash: if the file is empty, missing, or has wrong columns, print a clear error message instead
- Use fake data only for testing. Never real people's information