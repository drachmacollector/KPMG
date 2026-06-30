# MAHABOCW Medical Scholarship Verification Automation

**Version:** 2.0 (Revised Architecture)

**Project Type:** Intelligent Document Processing (IDP) + Browser Automation

**Language:** Python

**Target Users:** Maharashtra Building & Other Construction Workers Welfare Board (MAHABOCW)

**Status:** Active Development

---

# 1. Executive Summary

This project automates one of the most time-consuming verification tasks performed by the Maharashtra Building and Other Construction Workers Welfare Board (MAHABOCW) while processing educational assistance claims submitted by registered construction workers.

Applicants upload supporting documents such as Bonafide Certificates, College Identity Cards, Aadhaar Cards, Ration Cards and Self Declarations through the MAHABOCW portal. Unfortunately, the college information entered by applicants is frequently incomplete, abbreviated or incorrect.

Currently, consultants manually verify every application by opening the uploaded Bonafide Certificate, reading the college letterhead and manually correcting the college name and address inside an Excel sheet.

With more than 21,000 applications (and growing), this process is extremely repetitive and time consuming.

The objective of this project is to automate as much of this workflow as possible while maintaining a human-review mechanism for uncertain cases.

This project has evolved from a simple Playwright automation script into a complete Intelligent Document Processing (IDP) pipeline capable of:

- Automatically navigating the government portal
- Extracting uploaded document URLs
- Downloading applicant documents
- Normalizing different file formats
- Classifying document pages
- Performing OCR only where required
- Extracting structured information using a local LLM
- Writing corrected values back into Excel

No modifications are made to the government portal.

The only deliverable is a corrected Excel workbook.

---

# 2. Project Objectives

The primary objective is to automatically populate two new columns in the existing Excel workbook.

```

corrected_college_name

corrected_college_address

```

These values should represent the official institution name and address exactly as printed on the Bonafide Certificate (and optionally verified using the College Identity Card).

The original dataset must remain untouched.

The automation must simply generate a corrected copy of the workbook.

---

# 3. Scope

## In Scope

- Browser automation
- Portal navigation
- HTML parsing
- Downloading uploaded documents
- Processing PDFs and images
- OCR
- AI-based information extraction
- Excel updates
- Duplicate detection
- Logging
- Resume capability

## Out of Scope

- Editing records inside the government portal
- Automatic login
- Duplicate beneficiary detection (handled separately)
- Modifying uploaded applicant documents

---

# 4. Dataset

Primary Workbook

```

Medical_Claim_Data_Part_1.xlsx

```

Primary Worksheet

```

Medical Data Verification-Par1

```

Approximate Records

```

21,348

```

Relevant Columns

```

acknowledgement_no

child_name

academic_years

college_name

college_address

registration_no

aadhar_number

degree_name

```

Two additional columns will be added

```

corrected_college_name

corrected_college_address

```

---

# 5. Existing Problems

The dataset suffers from two independent problems.

## Problem 1 — Duplicate Beneficiaries

Some beneficiaries have applied multiple times during the same academic year.

This problem is being solved independently and is outside the scope of this project.

---

## Problem 2 — Incorrect College Information

This is the focus of the current project.

Applicants frequently enter

- abbreviated college names
- misspelled names
- incomplete addresses
- only the city name
- missing "& Hospital"
- missing locality

Example

Applicant entered

```

TAKHATMAL SHRIVALABH HOMOEOPATHIC MEDICAL COLLEGE

```

Official institution

```

TAKHATMAL SHRIVALLABH HOMOEOPATHIC MEDICAL COLLEGE & HOSPITAL

```

Applicant Address

```

AMRAVATI

```

Correct Address

```

RAJAPETH, AMRAVATI

```

The automation must extract the official institution details directly from the uploaded documents.

---

# 6. Current Manual Workflow

Every application currently follows exactly the same manual verification process.

## Step 1

Open

```

Medical_Claim_Data_Part_1.xlsx

```

Select one acknowledgement number.

Example

```

6834821252

```

---

## Step 2

Open

```

https://iwbms.mahabocw.in/sso

```

Login manually.

Automation intentionally does NOT automate login.

---

## Step 3

After login

User reaches

```

https://iwbms.mahabocw.in/administrator

```

Important finding

The website is an Angular Single Page Application (SPA).

The URL does not change while navigating through different sections.

---

## Step 4

Click

```

Claims

```

The browser still remains on

```

/administrator

```

because navigation occurs inside the Angular application.

---

## Step 5

The Claims grid appears.

Initially it does NOT contain the

```

Acknowledgement Number

```

column.

The user manually drags this column into the grid.

This only needs to be done once before automation begins.

---

## Step 6

Click the three horizontal menu bars on the

```

Acknowledgement Number

```

column.

Select

```

Filter

```

(the funnel icon)

A filter textbox appears.

Automation begins from this point onward.

---

# 7. Current Browser Automation

The Playwright script currently performs the following successfully.

For each row in Excel

Read

```

acknowledgement_no

```

↓

Type acknowledgement number into filter textbox

↓

Click

```

Apply

```

↓

Wait for filtering

↓

Click

```

View Claim Form

```

↓

Claim Form opens in a new browser tab.

At this stage browser automation is considered essentially complete.

The remainder of the project is now an Intelligent Document Processing problem rather than a browser automation problem.

---

# 8. Claim Form Structure

The claim page contains the following major sections

Worker Details

->

Beneficiary Details

->

Institute Details

->

Documents Required

The Documents Required section contains five uploaded documents.

1. Bonafide Certificate
2. College Identity Card
3. Aadhaar Card
4. Ration Card
5. Self Declaration

Only the Bonafide Certificate and College Identity Card are relevant for this project.
