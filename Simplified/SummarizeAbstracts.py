
import requests
import json
from pathlib import Path
from dataclasses import dataclass
from bs4 import BeautifulSoup
import configuration

# --------------------------------------------------
# Configuration
# --------------------------------------------------

DESCRIPTION = "Summarization of Collected Abstracts"

# HTML CSS selectors
ABSTRACT_SELECTOR = ".abstract"
TITLE_SELECTOR = "h4"
TEXT_SELECTOR = ".text"
LINK_SELECTOR = "a"
HTML_FILE = configuration.DATABASE_DIRECTORY + "/" + configuration.WEBPAGE

# Ollama model configuration
OLLAMA_URL = configuration.BASE_OLLAMA_URL + "/api/generate"
MODEL = configuration.MODEL
TEMPERATURE = configuration.TEMPERATURE
BATCH_SIZE = configuration.BATCH_SIZE # can vary directly with available memory

# Misc variables
OUTPUT_FILE = configuration.DATABASE_DIRECTORY + "/" + "Report.md"


@dataclass
class Abstract:
    id: str
    title: str
    abstract: str
    link: str


# --------------------------------------------------
# HTML extraction
# --------------------------------------------------

def extract_abstracts(html_file):
    """Extract title, abstract, and link from HTML."""

    html = Path(html_file).read_text(encoding="utf-8")

    soup = BeautifulSoup(html, "html.parser")

    abstracts = []

    elements = soup.select(ABSTRACT_SELECTOR)

    for i, element in enumerate(elements, start=1):

        title_element = element.select_one(TITLE_SELECTOR)
        abstract_element = element.select_one(TEXT_SELECTOR)
        link_element = element.select_one(LINK_SELECTOR)

        if not title_element or not abstract_element: continue

        title = title_element.get_text(" ", strip=True)
        abstract = abstract_element.get_text(" ", strip=True)

        link = ""

        if link_element: link = link_element.get("href", "")

        if title and abstract:
            abstracts.append(
                Abstract(
                    id=f"P{i:03d}",
                    title=title,
                    abstract=abstract,
                    link=link
                )
            )

    return abstracts


# --------------------------------------------------
# Ollama interface
# --------------------------------------------------

def ollama_generate(prompt, model, temperature=TEMPERATURE):

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature
        }
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=600
    )

    response.raise_for_status()

    return response.json()["response"].strip()


# --------------------------------------------------
# Individual abstract analysis
# --------------------------------------------------

def analyze_paper(abstract, model):

    prompt = f"""
You are an experienced senior research engineer.

Analyze the following scientific paper abstract.

PAPER ID: {abstract.id}

TITLE:
{abstract.title}

ABSTRACT:
{abstract.abstract}

Produce a structured analysis using these headings:

1. Research Objective
   What problem or question does the study address?

2. Research Methods
   What methods, technologies, or approaches are described?

3. Main Findings
   What are the most important findings?

4. Conclusions
   What conclusions are supported by the abstract?

5. Key Concepts
   List the important technical concepts and keywords.

6. Research Contribution
   What does this paper contribute to its research area?

7. Limitations
   Identify limitations explicitly stated in the abstract.
   If none are stated, say "Not specified in abstract."

IMPORTANT:
- Do not invent information.
- Do not plagiarize.
- Distinguish reported findings from interpretations.
- Use only information in the supplied abstract.
- If information is missing, state that it is not specified.
"""

    return ollama_generate(prompt, model)


# --------------------------------------------------
# Analyze all abstracts
# --------------------------------------------------

def analyze_all_abstracts(abstracts, model):

    results = []

    for i, abstract in enumerate(abstracts, start=1):

        print(
            f"Analyzing abstract {i}/{len(abstracts)}: "
            f"{abstract.title}"
        )

        analysis = analyze_paper(abstract, model)

        results.append({
            "abstract": abstract,
            "analysis": analysis
        })

    return results


# --------------------------------------------------
# Group analyses for synthesis
# --------------------------------------------------

def create_batches(items, batch_size=8):

    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


# --------------------------------------------------
# Synthesize a group of abstracts
# --------------------------------------------------

def synthesize_batch(batch, model):

    material = []

    for item in batch:

        abstract = item["abstract"]

        material.append(f"""
PAPER ID: {abstract.id}
TITLE: {abstract.title}
LINK: {abstract.link}

ANALYSIS:
{item["analysis"]}
""")

    prompt = f"""
You are an expert senior research engineer.

Synthesize the following individual paper analyses.

{chr(10).join(material)}

Identify information in these categories:

1. Main research themes.
2. Common research objectives.
3. Frequently used methods and technologies.
4. Agreements among studies.
5. Differences or conflicting findings.
6. Important research contributions.
7. Research limitations and knowledge gaps.
8. Emerging research directions.

For every category, identify the supporting
paper IDs, such as [P001] or [P004].

IMPORTANT REQUIREMENTS:

- Do not invent findings or references.
- Do not plagiarize.
- Distinguish evidence from interpretation.
"""

    return ollama_generate(prompt, model)


# --------------------------------------------------
# Final abstract synthesis
# --------------------------------------------------

def final_synthesis(batch_summaries, model):

    prompt = f"""
You are an experienced senior research engineer.

Prepare an integrated literature review based on
the following research synthesis results.

{chr(10).join(batch_summaries)}

Organize the review using these sections:

# 1. Overview of the Research Area

Describe the overall research topic and its importance.

# 2. Main Research Themes

Explain the major themes identified across the studies.

# 3. Research Methods and Technologies

Compare the methods and technologies used.

# 4. Common Findings

Explain the findings that are consistent across studies.

# 5. Differences and Contradictions

Identify disagreements, differences, and possible
reasons for conflicting findings.

# 6. Research Gaps

Identify areas that remain insufficiently investigated.

# 7. Future Research Directions

Suggest promising directions based on the identified gaps.

# 8. Overall Conclusions

Summarize the state of the research field.

IMPORTANT REQUIREMENTS:

- Maintain an academic writing style.
- Do not plagiarize.
- Avoid simply listing individual abstract summaries.
- Integrate findings across multiple studies.
- Attach abstract IDs to specific claims.
- Do not invent citations or research results.
- Clearly distinguish evidence from interpretation.
- Do not claim that the abstracts establish details
  that they do not actually report.
"""

    return ollama_generate(prompt, model, temperature=TEMPERATURE)


# --------------------------------------------------
# Generate Markdown report
# --------------------------------------------------

def write_markdown(
    abstracts,
    analyses,
    synthesis,
    output_file
):

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        f.write("# Abstract Review\n\n")

        f.write("## Integrated Research Synthesis\n\n")

        f.write(synthesis + "\n\n")

        f.write("---\n\n")

        f.write("# Individual Abstract Analyses\n\n")

        for item in analyses:

            abstract = item["abstract"]

            f.write(f"## [{abstract.id}] {abstract.title}\n\n")

            if abstract.link:
                f.write(f"**Link:** {abstract.link}\n\n")

            f.write(item["analysis"] + "\n\n")

            f.write("---\n\n")

        f.write("# Source abstracts\n\n")

        for abstract in abstracts:

            f.write(
                f"- [{abstract.id}] "
                f"{abstract.title}"
            )

            if abstract.link: f.write(f" - {abstract.link}")
            f.write("\n")


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    # 1. Extract abstracts
    abstracts = extract_abstracts(HTML_FILE)

    if not abstracts:
        raise RuntimeError(
            "No abstracts found. Check your HTML CSS selectors."
        )

    print(f"\nFound {len(abstracts)} abstracts.\n")

    # 2. Analyze each abstract
    analyses = analyze_all_abstracts(
        abstracts,
        MODEL
    )

    # 3. Save individual analyses
    Path(f"{configuration.DATABASE_DIRECTORY}/abstract_analyses.json").write_text(
        json.dumps(
            [
                {
                    "id": item["abstract"].id,
                    "title": item["abstract"].title,
                    "link": item["abstract"].link,
                    "analysis": item["analysis"]
                }
                for item in analyses
            ],
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    # 4. Create batches
    batches = list(
        create_batches(
            analyses,
            BATCH_SIZE
        )
    )

    # 5. Synthesize each batch
    batch_summaries = []

    for i, batch in enumerate(batches, start=1):

        print(
            f"\nSynthesizing group {i}/{len(batches)}..."
        )

        summary = synthesize_batch(
            batch,
            MODEL
        )

        batch_summaries.append(summary)

    # 6. Produce final integrated synthesis
    print("\nGenerating final abstract review...")

    synthesis = final_synthesis(
        batch_summaries,
        MODEL
    )

    # 7. Generate Markdown report
    write_markdown(
        abstracts,
        analyses,
        synthesis,
        OUTPUT_FILE
    )

    print("\nResearch synthesis completed.")

    print(f"Markdown report: {OUTPUT_FILE}")

    print(f"Individual analyses: {configuration.DATABASE_DIRECTORY}/abstract_analyses.json")
