# DAIL Forge Research Terminal Guide

## Overview

The **Research Terminal** is an interactive command-line interface integrated into DAIL Forge that allows researchers to query the AI litigation database using natural language commands. This provides a more intuitive and powerful way to search, filter, and export case data.

---

## Accessing the Terminal

1. Open DAIL Forge in your browser: **http://localhost:8000**
2. Click the **💻 Terminal** tab in the navigation bar
3. Start typing commands in the input field at the bottom

---

## Quick Start

### Step 1 — Open the Terminal
Navigate to the Terminal tab. You'll see a command prompt ready for input.

### Step 2 — Search Cases
Type natural language queries like:
```
cases about privacy in California
```

### Step 3 — Get Results
The terminal displays matching cases with key details, tags, and metadata.

### Step 4 — Drill Down
View full details for any case:
```
show case 127
```

### Step 5 — Export for Analysis
Export your results instantly:
```
export csv
```

---

## Available Commands

### Basic Commands

| Command | Description | Example |
|---------|-------------|---------|
| `help` or `?` | Show available commands | `help` |
| `clear` or `cls` | Clear the terminal screen | `clear` |
| `stats` | Display database statistics | `stats` |

### Search Commands

#### Show Specific Case
```bash
show case 127
get case 42
view case 1
```

Displays complete details including:
- Case metadata (name, court, dates, status)
- Associated documents
- Secondary sources
- Tags and classification
- Stub status

#### Search with Natural Language

The terminal intelligently parses natural language queries. Here are examples:

**Search by Keyword:**
```bash
cases about privacy
search facial recognition
find employment discrimination cases
```

**Search by Location:**
```bash
cases in California
show cases from 9th Circuit
list federal court cases
cases in district court
```

**Search by Date:**
```bash
cases filed after 2022
show cases from 2020-01-01
cases before 2023
cases after 2022-01-01
```

**Search by Status:**
```bash
cases with status active
show active cases
list closed cases
```

**Search by Outcome:**
```bash
cases with outcome settled
show dismissed cases
```

**Combined Searches:**
```bash
privacy cases in California after 2022
employment discrimination and AI cases
facial recognition cases in federal court
generative AI cases with status active
```

### Export Commands

| Command | Description | Output |
|---------|-------------|--------|
| `export csv` | Export last search results as CSV | Downloads `cases.csv` |
| `csv` | Shortcut for CSV export | Downloads `cases.csv` |
| `export json` | Export last search results as JSON | Downloads `dail-cases.json` |
| `json` | Shortcut for JSON export | Downloads `dail-cases.json` |

**Note:** You must run a search query first before exporting results.

---

## Natural Language Query Examples

### By Topic
```bash
# Privacy-related cases
cases about privacy

# AI and employment issues
employment discrimination and AI

# Facial recognition technology
facial recognition cases

# Generative AI
generative AI litigation
```

### By Geography
```bash
# California state courts
privacy cases in California

# Federal appeals court
cases in 9th Circuit

# Federal district courts
federal court cases about AI

# Specific court
cases from Cal. Los Angeles County Super. Ct.
```

### By Time Period
```bash
# Recent cases
cases filed after 2023

# Specific year
show cases from 2022

# Date range
cases after 2020-01-01

# Before a date
cases filed before 2021
```

### By Status/Outcome
```bash
# Active litigation
cases with status active

# Concluded cases
show closed cases

# Settlement outcomes
cases with outcome settled

# Dismissed cases
dismissed cases
```

### Complex Queries
```bash
# Multiple filters
privacy cases in California after 2022

# Topic + jurisdiction + time
facial recognition in federal court after 2021

# Topic + status
generative AI cases with status active

# Full combination
employment discrimination cases in 9th Circuit after 2020
```

---

## Understanding Results

### Search Results Display

When you run a search, the terminal shows:

1. **Total Count**: How many cases match your query
2. **Case List**: Up to 10 cases per page with:
   - **ID Number**: Database identifier (e.g., #127)
   - **Case Name**: Official case caption
   - **Court**: Jurisdiction where filed
   - **Filing Date**: When the case was initiated
   - **Tags**: Issue areas, topics, algorithms, etc.
   - **Stub Indicator**: Shows if it's a synthesized stub record

3. **Export Options**: Quick button to download results as CSV

### Case Detail View

When viewing a specific case with `show case [id]`:

```
Case #127 Details:
├── Name: Justine Hsu v. Tesla, Inc.
├── Court: Cal. Los Angeles County Super. Ct.
├── Filing Date: 2020-05-14
├── Status: Open
├── Tags: issue: Privacy, area: Employment
├── Documents (3):
│   ├── Complaint (link)
│   ├── Motion to Dismiss (link)
│   └── Opposition Brief (link)
└── Secondary Sources (2):
    ├── News Article - TechCrunch (link)
    └── Law Review Article (link)
```

---

## Terminal Features

### Command History
- **↑ Arrow Key**: Navigate to previous commands
- **↓ Arrow Key**: Navigate to next commands
- **Enter**: Execute current command

### Auto-Scroll
The terminal automatically scrolls to show the latest results.

### Smart Parsing
The system understands variations in phrasing:
- "cases about privacy" = "privacy cases" = "search privacy"
- "in California" = "from California" = "California cases"
- "after 2022" = "since 2022" = "from 2022"

### Export Shortcuts
After any search, you can immediately export results:
- Click the "⬇ Export CSV" button in results
- Type `export csv` or just `csv`
- Type `export json` for JSON format

---

## Use Cases for Researchers

### 1. Exploratory Research
```bash
# Start broad
stats

# Narrow down by topic
cases about generative AI

# Refine by location
generative AI cases in federal court

# Add time filter
generative AI cases in federal court after 2023

# Export for analysis
export csv
```

### 2. Specific Case Investigation
```bash
# Search by keyword
cases about Tesla privacy

# Find the case ID from results
# Then get full details
show case 127

# Review documents and sources in the output
```

### 3. Trend Analysis
```bash
# Get all privacy cases
privacy cases

# Note the count and export
export csv

# Compare to facial recognition
facial recognition cases

# Export again
export csv

# Analyze both datasets in Excel/Python/R
```

### 4. Jurisdiction Comparison
```bash
# California cases
privacy cases in California
export csv

# Federal cases
privacy cases in federal court
export csv

# Compare the two exports
```

### 5. Temporal Analysis
```bash
# Before 2022
AI cases before 2022
export csv

# After 2022
AI cases after 2022
export csv

# Analyze trends over time
```

---

## Data Export Formats

### CSV Export
- Clean, ready-to-use format
- All case metadata in columns
- Tags combined in single field as `type:value; type:value`
- Perfect for Excel, R, Python pandas
- No manual cleanup needed

### JSON Export
- Complete structured data
- Nested objects for tags, documents, sources
- Ideal for programmatic analysis
- Easy to parse with Python, JavaScript, etc.

---

## Tips & Best Practices

1. **Start with `help`**: Get familiar with available commands
2. **Use `stats`**: Understand what data is available before searching
3. **Be specific**: Combine multiple filters for precise results
4. **Export early**: Save your results before refining searches
5. **Use short keywords**: "privacy" works better than "privacy-related issues"
6. **Check stub status**: Orange "STUB" label indicates synthesized records
7. **Explore case details**: Use `show case [id]` to see full information
8. **Command history**: Use arrow keys to repeat/modify previous searches

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Execute command |
| `↑` | Previous command |
| `↓` | Next command |
| `Ctrl+C` | (Not implemented - use `clear` to reset) |

---

## Comparing to Traditional Approach

### Before (Traditional UI)
❌ Navigate through multiple filter dropdowns  
❌ Remember exact field names  
❌ Export messy data requiring cleanup  
❌ Limited to predefined filter combinations  
❌ Difficult to repeat searches

### Now (Terminal)
✅ Type natural language queries  
✅ Flexible search combinations  
✅ Clean, analysis-ready exports  
✅ Command history for repeatability  
✅ Instant results with one command

---

## Example Research Workflow

```bash
# 1. Check what's available
$ stats

# 2. Explore a topic
$ cases about facial recognition

# Found 47 cases (showing 10):
# #234 Tech Workers Coalition v. Amazon
# #156 ACLU v. Clearview AI
# ...

# 3. Narrow by jurisdiction
$ facial recognition cases in federal court

# Found 23 cases (showing 10):
# ...

# 4. Export for analysis
$ export csv

# Downloading CSV export...

# 5. Look at a specific case
$ show case 156

# Case #156 Details:
# Name: ACLU v. Clearview AI
# ...
# Documents (12):
# ...

# 6. Try different search
$ generative AI cases after 2023

# Found 8 cases (showing 8):
# ...

# 7. Export again
$ export json

# Downloaded 8 cases as JSON
```

---

## Integration with DAIL Forge

The Terminal seamlessly integrates with the existing DAIL Forge features:

- **Same Data**: Queries the same PostgreSQL database
- **Same API**: Uses the existing research endpoints
- **Same Filters**: All filter options available via natural language
- **Provenance**: Results include provenance indicators (stub status)
- **Export Compatibility**: CSV exports match the API export format

You can switch between the Terminal and other DAIL Forge pages (Cases Browser, Dashboard, etc.) at any time.

---

## Advanced Tips

### Precise Date Filtering
```bash
# Full date format
cases after 2022-06-15

# Year only (expands to Jan 1)
cases after 2022
```

### Court Matching
The terminal matches partial court names:
```bash
california    # Matches "Cal. Los Angeles County..."
federal       # Matches "U.S. District Court..."
9th           # Matches "9th Circuit..."
district      # Matches any district court
```

### Keyword Matching
Keywords search across:
- Case name/caption
- Plaintiff name
- Defendant name
- Case summary

```bash
cases about Amazon  # Searches all those fields
```

---

## Troubleshooting

### "No cases found"
- Broaden your search terms
- Check spelling
- Try `stats` to see available data
- Remove some filters

### Export shows "No previous search results"
- Run a search query first
- Export command only works after a search

### Results seem incomplete
- Default page size is 10 cases
- Use CSV export to get all matching results
- Full database statistics available via `stats`

---

## Future Enhancements (Roadmap)

Potential future features:
- Pagination control (`page 2`, `next`, `prev`)
- Sort options (`sort by date`, `sort by court`)
- Tag-specific searches (`tag:privacy`, `area:employment`)
- Boolean operators (`privacy AND employment`, `tesla OR amazon`)
- Wildcard searches (`*recognition*`)
- Saved queries/bookmarks
- Result highlighting
- Case comparison mode

---

## Getting Help

1. **In Terminal**: Type `help` to see all commands
2. **API Documentation**: Click "📄 API Docs" in the navigation for technical details
3. **Architecture**: See the "🏗️ Architecture" page for system overview
4. **Dashboard**: View overall statistics on the Dashboard page

---

## Summary

The DAIL Forge Research Terminal provides:

✅ **Natural Language Search** — Query like you think  
✅ **Instant Results** — Fast, filtered case lists  
✅ **One-Command Export** — Clean CSV/JSON downloads  
✅ **Case Deep-Dive** — Full details for any case  
✅ **Command History** — Repeat and refine searches  
✅ **Research-Ready Data** — No cleanup needed

**Start using it now:** http://localhost:8000 → Click "💻 Terminal"
