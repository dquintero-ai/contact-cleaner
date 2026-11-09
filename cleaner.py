# Contact Cleaner
# Cleans a messy contact spreadsheet, rejects bad rows, then removes duplicates.
# The original file is only read. Results are written into the output folder.

import csv
import datetime
import html
import os
import re
import sys

# The five columns every input file must have, in this order.
COLUMNS = ["name", "email", "phone", "company", "city"]

# Words that mean "nothing was entered", no matter how they are capitalized.
PLACEHOLDERS = {
    "n/a",
    "na",
    "#n/a",
    "n.a",
    "n.a.",
    "null",
    "none",
    "nil",
    "undefined",
    "-",
    "--",
}

# A valid email is some text, an @ sign, and a domain that contains a dot.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# Run the cleaner on the CSV file named after the command.
def main():
    if len(sys.argv) != 2:
        print("Please give one CSV file. Example: python cleaner.py sample_messy.csv")
        return

    rows, error = read_contacts(sys.argv[1])
    if error:
        print(error)
        return

    prepared = []
    phones_blanked = 0
    for index, original in enumerate(rows):
        cleaned, phone_was_blanked = clean_contact(original)
        if phone_was_blanked:
            phones_blanked += 1
        prepared.append({
            "index": index,
            "original": original,
            "cleaned": cleaned,
        })

    rejected = []
    eligible = []
    for contact in prepared:
        reason = rejection_reason(contact["cleaned"])
        if reason:
            contact["reason"] = reason
            rejected.append(contact)
        else:
            eligible.append(contact)

    kept, duplicates = remove_duplicates(eligible)
    for contact in kept:
        contact["outcome"] = "Kept"
    for contact in duplicates:
        contact["outcome"] = "Removed as duplicate"
    for contact in rejected:
        contact["outcome"] = "Rejected"

    make_output_folder()
    write_clean_file(kept)
    write_rejected_file(rejected)
    write_report(
        sys.argv[1],
        prepared,
        duplicates,
        rejected,
        len(rows),
        len(kept),
        len(duplicates),
        len(rejected),
        phones_blanked,
    )
    print_summary(
        len(rows),
        len(kept),
        len(duplicates),
        len(rejected),
        phones_blanked,
    )


# Read the CSV without changing it. Return the rows, or a short error message.
def read_contacts(path):
    if not os.path.isfile(path):
        return None, f"Could not find the file: {path}"

    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            if handle.read().strip() == "":
                return None, "The file is empty. There are no contacts to clean."
            handle.seek(0)
            reader = csv.reader(handle)
            header = next(reader, None)
    except OSError:
        return None, f"Could not read the file: {path}"
    except csv.Error:
        return None, f"Could not read that file as a CSV: {path}"

    if header is None:
        return None, "The file is empty. There are no contacts to clean."

    header = [cell.strip() for cell in header]
    if header != COLUMNS:
        found = ", ".join(header) if any(header) else "(no columns)"
        return None, (
            "The columns are not right. Expected name, email, phone, company, city. "
            f"Found: {found}"
        )

    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for cells in reader:
                # A blank line is not a contact. A row of empty cells is.
                if cells is None:
                    continue
                values = [cells.get(column) or "" for column in COLUMNS]
                if len(cells) == 0:
                    continue
                rows.append({
                    "name": values[0],
                    "email": values[1],
                    "phone": values[2],
                    "company": values[3],
                    "city": values[4],
                })
    except OSError:
        return None, f"Could not read the file: {path}"
    except csv.Error:
        return None, f"Could not read that file as a CSV: {path}"

    if not rows:
        return None, "The file is empty. There are no contacts to clean."
    return rows, ""


# Trim extra spaces, then treat placeholder words as an empty value.
def tidy_text(value):
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text.strip())
    if text.lower() in PLACEHOLDERS:
        return ""
    return text


# Turn one raw contact into clean name, email, phone, company, and city values.
def clean_contact(original):
    name = tidy_text(original["name"])
    if name:
        name = name.title()

    email = tidy_text(original["email"]).lower()
    phone, phone_was_blanked = clean_phone(original["phone"])
    company = tidy_text(original["company"])
    city = tidy_text(original["city"])

    cleaned = {
        "name": name,
        "email": email,
        "phone": phone,
        "company": company,
        "city": city,
    }
    return cleaned, phone_was_blanked


# Keep a 10-digit US number, or an 11-digit number that starts with 1.
# Any other real phone value is wiped and reported as blanked.
def clean_phone(raw_phone):
    text = tidy_text(raw_phone)
    if text == "":
        return "", False

    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    if len(digits) == 10:
        formatted = f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"
        return formatted, False

    return "", True


# Check that an email has text, an @ sign, and a domain with a dot.
def valid_email(email):
    return EMAIL_PATTERN.fullmatch(email) is not None


# List every reason a cleaned row should be rejected. A blank email is allowed.
def rejection_reason(cleaned):
    reasons = []
    if cleaned["name"] == "":
        reasons.append("missing name")
    if cleaned["email"] != "" and not valid_email(cleaned["email"]):
        reasons.append("invalid email")
    if cleaned["email"] == "" and cleaned["phone"] == "":
        reasons.append("no email and no phone")
    return "; ".join(reasons)


# Count how many of the five contact fields have a value.
def filled_count(cleaned):
    count = 0
    for column in COLUMNS:
        if cleaned[column] != "":
            count += 1
    return count


# Two people match when they share an email or a phone. Blank values do not count.
def same_person(left, right):
    same_email = left["email"] != "" and left["email"] == right["email"]
    same_phone = left["phone"] != "" and left["phone"] == right["phone"]
    return same_email or same_phone


# Group rows that are the same person, then keep the fullest row in each group.
# When two rows are equally full, keep the one that appeared first in the file.
def remove_duplicates(contacts):
    groups = []
    for contact in contacts:
        matching_groups = []
        other_groups = []
        for group in groups:
            shares_identity = False
            for other in group:
                if same_person(contact["cleaned"], other["cleaned"]):
                    shares_identity = True
                    break
            if shares_identity:
                matching_groups.append(group)
            else:
                other_groups.append(group)

        if not matching_groups:
            groups.append([contact])
            continue

        merged = [contact]
        for group in matching_groups:
            merged.extend(group)
        groups = other_groups + [merged]

    kept = []
    removed = []
    for group in groups:
        winner = group[0]
        for contact in group[1:]:
            contact_score = filled_count(contact["cleaned"])
            winner_score = filled_count(winner["cleaned"])
            contact_is_fuller = contact_score > winner_score
            contact_is_earlier_tie = (
                contact_score == winner_score
                and contact["index"] < winner["index"]
            )
            if contact_is_fuller or contact_is_earlier_tie:
                winner = contact
        kept.append(winner)
        for contact in group:
            if contact is not winner:
                contact["kept_with"] = winner
                removed.append(contact)

    kept.sort(key=lambda contact: contact["index"])
    removed.sort(key=lambda contact: contact["index"])
    return kept, removed


# Create the output folder if it is not already there.
def make_output_folder():
    os.makedirs("output", exist_ok=True)


# Save the kept contacts with the same five columns as the input.
def write_clean_file(contacts):
    path = os.path.join("output", "contacts_clean.csv")
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for contact in contacts:
            writer.writerow(contact["cleaned"])


# Save rejected rows using the original messy values, plus a reason column.
def write_rejected_file(contacts):
    path = os.path.join("output", "contacts_rejected.csv")
    fieldnames = COLUMNS + ["reason"]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for contact in contacts:
            row = dict(contact["original"])
            row["reason"] = contact["reason"]
            writer.writerow(row)


# Print the five summary numbers. Rows in equals clean plus duplicates plus rejected.
def print_summary(rows_in, clean_rows, duplicates_removed, rows_rejected, phones_blanked):
    print(f"Rows in: {rows_in}")
    print(f"Clean rows out: {clean_rows}")
    print(f"Duplicates removed: {duplicates_removed}")
    print(f"Rows rejected: {rows_rejected}")
    print(f"Phones blanked (including rejected rows): {phones_blanked}")


# Styles for the client report. Kept apart from the HTML so the braces stay literal.
REPORT_CSS = """
:root {
  --ink: #1c2830;
  --muted: #5c6b76;
  --line: #d5dee4;
  --paper: #eef2f4;
  --card: #ffffff;
  --navy: #16324f;
  --highlight: #fff4cc;
  --match: #e5f4f2;
  --empty: #6b7780;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  font-size: 16px;
  line-height: 1.5;
}
a { color: var(--navy); }
.banner {
  background: var(--navy);
  color: #f7fafc;
  padding: 40px 24px 32px;
}
.banner-inner, main { max-width: 1100px; margin: 0 auto; }
.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #b7c9d6;
}
h1 { margin: 0 0 8px; font-size: 34px; font-weight: 650; letter-spacing: -0.02em; }
.banner p { margin: 0; color: #d5e2ea; }
.contents { margin-top: 18px; font-size: 14px; }
.contents a { color: #ffffff; margin-right: 16px; }
main { padding: 28px 24px 64px; }
section {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 28px;
  margin-bottom: 22px;
}
h2 { margin: 0 0 8px; font-size: 22px; letter-spacing: -0.01em; }
.section-kicker {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.intro { margin: 0 0 18px; color: var(--muted); }
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.stat {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 16px 16px 14px;
  background: #fbfcfd;
}
.stat.wide { grid-column: 1 / -1; }
.stat .number { display: block; font-size: 32px; font-weight: 650; letter-spacing: -0.03em; }
.stat .label { display: block; margin-top: 4px; color: var(--muted); font-size: 14px; }
.equation {
  margin: 16px 0 0;
  padding: 12px 14px;
  background: #f4f7f8;
  border-radius: 8px;
  font-size: 15px;
}
.note { margin: 10px 0 0; color: var(--muted); font-size: 14px; }
.legend { margin: 0 0 12px; font-size: 14px; color: var(--muted); }
.swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 6px;
  border-radius: 2px;
  vertical-align: -1px;
}
.swatch.changed { background: var(--highlight); box-shadow: inset 3px 0 0 #e2b340; }
.swatch.matched { background: var(--match); box-shadow: inset 3px 0 0 #1f6f6a; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { background: #f4f7f8; font-weight: 650; white-space: nowrap; }
.as-typed { white-space: pre-wrap; word-break: break-word; }
td.changed { background: var(--highlight); box-shadow: inset 3px 0 0 #e2b340; }
td.matched { background: var(--match); box-shadow: inset 3px 0 0 #1f6f6a; }
.row-id { width: 92px; font-weight: 650; background: #fbfcfd; }
.when { width: 72px; color: var(--muted); font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }
.outcome {
  display: inline-block;
  margin-top: 6px;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
}
.pair {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 14px;
}
.pair h3 { margin: 0 0 4px; font-size: 16px; }
.pair p { margin: 0 0 12px; color: var(--muted); font-size: 14px; }
.empty { color: var(--empty); font-style: italic; }
.badge {
  display: inline-block;
  margin: 0 6px 4px 0;
  padding: 3px 8px;
  border-radius: 999px;
  background: #fde8e4;
  color: #8a2e14;
  font-size: 12px;
  font-weight: 650;
}
footer { color: var(--muted); font-size: 13px; }
@media (max-width: 800px) {
  .stats { grid-template-columns: 1fr 1fr; }
  h1 { font-size: 28px; }
  section { padding: 20px; }
}
"""


# Turn a spreadsheet row number into the line a person would see in the file.
def spreadsheet_row(contact):
    return contact["index"] + 2


# Return True when cleaning changed at least one cell in this contact.
def row_was_changed(contact):
    for column in COLUMNS:
        if contact["original"][column] != contact["cleaned"][column]:
            return True
    return False


# Turn a contact field into safe HTML. Blank fields are labeled so they stay visible.
def show_value(value):
    if value is None or str(value) == "":
        return '<span class="empty">(empty)</span>'
    return html.escape(str(value), quote=True)


# Say whether two cleaned contacts matched on email, phone, or both.
def match_phrase(kept, removed):
    left = kept["cleaned"]
    right = removed["cleaned"]
    matched_email = left["email"] != "" and left["email"] == right["email"]
    matched_phone = left["phone"] != "" and left["phone"] == right["phone"]
    if matched_email and matched_phone:
        return "Same email and phone number after cleaning."
    if matched_email:
        return "Same email after cleaning."
    if matched_phone:
        return "Same phone number after cleaning."
    return "Matched after cleaning."


# List the cleaned fields that made these two rows count as the same person.
def matched_columns(kept, removed):
    left = kept["cleaned"]
    right = removed["cleaned"]
    columns = []
    if left["email"] != "" and left["email"] == right["email"]:
        columns.append("email")
    if left["phone"] != "" and left["phone"] == right["phone"]:
        columns.append("phone")
    return columns


# Explain why one row was kept and the other was removed.
def keep_reason(kept, removed):
    kept_score = filled_count(kept["cleaned"])
    removed_score = filled_count(removed["cleaned"])
    if kept_score > removed_score:
        return (
            f"The kept row has more filled-in fields "
            f"({kept_score} of 5, compared with {removed_score} of 5)."
        )
    return (
        "Both rows have the same number of filled-in fields. "
        "The earlier row in the file was kept."
    )


# Build the summary, including the check that every input row is accounted for.
def summary_section(source_name, rows_in, clean_rows, duplicates_removed, rows_rejected, phones_blanked):
    equation = (
        f"{rows_in} rows in = {clean_rows} clean rows "
        f"+ {duplicates_removed} duplicates removed "
        f"+ {rows_rejected} rows rejected"
    )
    return f"""
    <section id="summary">
      <p class="section-kicker">01 · Summary</p>
      <h2>Summary</h2>
      <p class="intro">Results for {html.escape(source_name)}. The input file was not changed.</p>
      <div class="stats">
        <div class="stat"><span class="number">{rows_in}</span><span class="label">Rows in</span></div>
        <div class="stat"><span class="number">{clean_rows}</span><span class="label">Clean rows out</span></div>
        <div class="stat"><span class="number">{duplicates_removed}</span><span class="label">Duplicates removed</span></div>
        <div class="stat"><span class="number">{rows_rejected}</span><span class="label">Rows rejected</span></div>
        <div class="stat wide"><span class="number">{phones_blanked}</span><span class="label">Phones blanked (including rejected rows)</span></div>
      </div>
      <p class="equation">{html.escape(equation)}</p>
      <p class="note">A phone is blanked when the digits cannot be turned into a US number. Placeholder words such as N/A, null, none, and - are treated as empty and are not included in that count. This count includes rows that were later rejected.</p>
    </section>
    """


# Build the before/after table. Unchanged rows are left out, and changed cells are marked.
def changes_section(contacts):
    changed_rows = [contact for contact in contacts if row_was_changed(contact)]
    if not changed_rows:
        body = "<p class=\"intro\">No values needed cleaning.</p>"
    else:
        body_rows = []
        for contact in changed_rows:
            before_cells = []
            after_cells = []
            for column in COLUMNS:
                changed = contact["original"][column] != contact["cleaned"][column]
                marker = " changed" if changed else ""
                before_cells.append(
                    f'<td class="as-typed{marker}">{show_value(contact["original"][column])}</td>'
                )
                after_cells.append(
                    f'<td class="as-typed{marker}">{show_value(contact["cleaned"][column])}</td>'
                )
            row_number = spreadsheet_row(contact)
            outcome = html.escape(contact.get("outcome", ""))
            body_rows.append(
                "<tr>"
                f'<td class="row-id" rowspan="2">Row {row_number}'
                f'<span class="outcome">{outcome}</span></td>'
                '<td class="when">Before</td>'
                + "".join(before_cells)
                + "</tr>"
                "<tr>"
                '<td class="when">After</td>'
                + "".join(after_cells)
                + "</tr>"
            )
        count = len(changed_rows)
        noun = "row" if count == 1 else "rows"
        body = f"""
        <p class="intro">{count} {noun} changed. Rows that were already clean are not listed.</p>
        <p class="legend"><span class="swatch changed"></span>Highlighted cells are the values that changed.</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Row</th>
                <th></th>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Company</th>
                <th>City</th>
              </tr>
            </thead>
            <tbody>
              {"".join(body_rows)}
            </tbody>
          </table>
        </div>
        """
    return f"""
    <section id="changes">
      <p class="section-kicker">02 · Changes</p>
      <h2>Changes</h2>
      {body}
    </section>
    """


# Build one comparison table for a removed duplicate and the row that was kept.
def duplicate_block(removed):
    kept = removed["kept_with"]
    shared = matched_columns(kept, removed)
    field_rows = []
    for column in COLUMNS:
        marker = " matched" if column in shared else ""
        field_rows.append(
            "<tr>"
            f"<th>{html.escape(column.title())}</th>"
            f'<td class="as-typed{marker}">{show_value(kept["cleaned"][column])}</td>'
            f'<td class="as-typed{marker}">{show_value(removed["cleaned"][column])}</td>'
            "</tr>"
        )
    kept_row = spreadsheet_row(kept)
    removed_row = spreadsheet_row(removed)
    return f"""
    <article class="pair">
      <h3>Row {removed_row} removed, next to kept row {kept_row}</h3>
      <p>{html.escape(match_phrase(kept, removed))} {html.escape(keep_reason(kept, removed))}</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Field</th>
              <th>Kept · row {kept_row}</th>
              <th>Removed · row {removed_row}</th>
            </tr>
          </thead>
          <tbody>
            {"".join(field_rows)}
          </tbody>
        </table>
      </div>
    </article>
    """


# Show each removed duplicate beside the row that was kept.
def duplicates_section(duplicates):
    if not duplicates:
        body = "<p class=\"intro\">No duplicate rows were removed.</p>"
    else:
        count = len(duplicates)
        noun = "duplicate was" if count == 1 else "duplicates were"
        blocks = "".join(duplicate_block(removed) for removed in duplicates)
        body = f"""
        <p class="intro">{count} {noun} removed. Each removed row is shown beside the row that was kept. These are the cleaned values, which is how the rows were compared.</p>
        <p class="legend"><span class="swatch matched"></span>Highlighted cells are the email or phone that matched.</p>
        {blocks}
        """
    return f"""
    <section id="duplicates">
      <p class="section-kicker">03 · Duplicates</p>
      <h2>Duplicates</h2>
      {body}
    </section>
    """


# Turn "missing name; invalid email" into separate reason labels.
def reason_badges(reason):
    parts = [part.strip() for part in reason.split(";") if part.strip()]
    badges = []
    for part in parts:
        badges.append(f'<span class="badge">{html.escape(part)}</span>')
    return "".join(badges)


# List every rejected row with its original messy values and the reason it was removed.
def rejected_section(rejected):
    if not rejected:
        body = "<p class=\"intro\">No rows were rejected.</p>"
    else:
        body_rows = []
        for contact in rejected:
            cells = []
            for column in COLUMNS:
                cells.append(
                    f'<td class="as-typed">{show_value(contact["original"][column])}</td>'
                )
            row_number = spreadsheet_row(contact)
            body_rows.append(
                "<tr>"
                f'<td class="row-id">Row {row_number}</td>'
                + "".join(cells)
                + f"<td>{reason_badges(contact['reason'])}</td>"
                + "</tr>"
            )
        count = len(rejected)
        noun = "row was" if count == 1 else "rows were"
        body = f"""
        <p class="intro">{count} {noun} rejected. The cells below are the original values, before cleaning.</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Row</th>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Company</th>
                <th>City</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {"".join(body_rows)}
            </tbody>
          </table>
        </div>
        """
    return f"""
    <section id="rejected">
      <p class="section-kicker">04 · Rejected</p>
      <h2>Rejected</h2>
      {body}
    </section>
    """


# Write the client report to output/report.html.
def write_report(source_path, contacts, duplicates, rejected, rows_in, clean_rows, duplicates_removed, rows_rejected, phones_blanked):
    source_name = os.path.basename(source_path)
    today = datetime.date.today()
    pretty_date = f"{today:%B} {today.day}, {today.year}"
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Contact cleaning report</title>
  <style>
{REPORT_CSS}
  </style>
</head>
<body>
  <header class="banner">
    <div class="banner-inner">
      <p class="eyebrow">Contact Cleaner</p>
      <h1>Contact cleaning report</h1>
      <p>{html.escape(source_name)} · {html.escape(pretty_date)}</p>
      <p class="contents">
        <a href="#summary">Summary</a>
        <a href="#changes">Changes</a>
        <a href="#duplicates">Duplicates</a>
        <a href="#rejected">Rejected</a>
      </p>
    </div>
  </header>
  <main>
    {summary_section(source_name, rows_in, clean_rows, duplicates_removed, rows_rejected, phones_blanked)}
    {changes_section(contacts)}
    {duplicates_section(duplicates)}
    {rejected_section(rejected)}
    <footer>Prepared for review. Clean contacts are in contacts_clean.csv. Rejected rows are in contacts_rejected.csv.</footer>
  </main>
</body>
</html>
"""
    path = os.path.join("output", "report.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document)


if __name__ == "__main__":
    main()
