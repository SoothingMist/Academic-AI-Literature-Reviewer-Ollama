
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama
import json, os
from bs4 import BeautifulSoup
import DatabaseFunctions
import paper_discovery
import configuration

llm = ChatOllama(
    base_url = configuration.BASE_OLLAMA_URL,
    model = configuration.MODEL,
    temperature = configuration.TEMPERATURE
)

document_records_table = "DocumentRecords"
query_records_table = "QueryRecords"


def remove_html_tags(html_content):
  """
  Remove all HTML tags from a string and return plain text.

  Args:
      html_content (str): The HTML string to clean.

  Returns:
      str: The plain text with all tags removed.
  """
  if not isinstance(html_content, str):
    raise TypeError("Input must be a string.")

  # Parse HTML and extract text
  soup = BeautifulSoup(html_content, "html.parser")
  return soup.get_text(separator=" ", strip=True)


def ConnectDatabase(databaseDirectory = configuration.DATABASE_DIRECTORY):
  # Create the archive directory if it does not exist.
  if not os.path.exists(databaseDirectory):
    os.makedirs(databaseDirectory)
    print(f"Created directory: {databaseDirectory}")
  # Connect to the database
  databaseFilename = f"{databaseDirectory}/database.db"
  databaseConnection = DatabaseFunctions.create_connection(databaseFilename)
  if databaseConnection is None:
    print("ConnectDatabase: Cannot continue. There is no connected database.")
  return databaseConnection

database_connection = ConnectDatabase()
if database_connection is None:
  print("Configuration Error: No connection to database.")
  exit(1)

def EstablishDocumentsTable(databaseConnection = database_connection,
                            tableName = document_records_table):
  DocumentsTable = f"""
                    CREATE TABLE IF NOT EXISTS {tableName}
                    (
                      Title     TEXT NOT NULL,
                      Abstract  TEXT NOT NULL,
                      URL       TEXT NOT NULL,
                      PRIMARY KEY (Title)
                    );
                   """
  # If table does not exist, create it.
  DatabaseFunctions.create_table(databaseConnection, DocumentsTable)

def EstablishQueryTable(databaseConnection = database_connection,
                        tableName = query_records_table):
  DocumentsTable = f"""
                    CREATE TABLE IF NOT EXISTS {tableName}
                    (
                      Query TEXT NOT NULL,
                      PRIMARY KEY (Query)
                    );
                   """
  # If table does not exist, create it.
  DatabaseFunctions.create_table(databaseConnection, DocumentsTable)

def GenerateSearchQueries():
  system_prompt =\
    f"""You are an experienced senior research engineer planning a literature review.
  
    ================ STEP 1: SCOPE EXTRACTION ================
    
    While responding to the human message and designing focus areas, identify what the question is
    specifically asking about. The question may carry constraints — population,
    intervention, outcome domain, time horizon, methodology, or none — that
    define the SCOPE of an answer that would actually satisfy the user.
    
    Write out the scope you identify. Be specific. For example, if the question
    mentions "healthy adults," that is the population scope and ALL searches must
    respect it. If it specifies a particular drug, treatment, or technique, that
    is the intervention scope. If it implies a particular outcome, that is the
    outcome scope.
    
    If the question is genuinely broad and has no explicit constraints, say so —
    then you can vary more freely. But do not invent constraints that aren't
    in the question, and do not ignore constraints that ARE in the question.
    
    ================ STEP 2: DESIGN 5 FOCUS AREAS ================
    
    Each focus area targets a DIFFERENT aspect of the research question WITHIN
    the scope you identified. Each gets ONE academic-database search query.
    
    CRITICAL: every focus area must stay within the scope. Do not introduce
    populations, interventions, or outcomes the user did not ask about.
    
    What dimensions to vary across depends on the QUESTION. Choose the
    dimensions that are actually relevant. Possible angles include:
    - Different specific outcomes within the asked-about domain
    - Different mechanisms or pathways that inform the answer
    - Different time horizons if relevant
    - Different study types (RCT, observational, systematic review)
    - Different sub-aspects of the intervention itself
    
    Do not force the same dimensions onto every question.
    
    ================ STEP 3: OUTPUT ================
    
    Respond with ONLY a JSON object:
    {{
        "identified_scope": "explicit description of the scope/constraints the question carries",
        "query_type": "broad|niche|specific|comparative",
        "academic_field": "primary field of study",
        "methodology_notes": "what study types are most relevant",
        "search_strategy": "your overall approach in 1-2 sentences, anchored to the scope",
        "focus_areas": [
            {{"area": "what aspect this targets (within scope)", "priority": 5, "search_query": "3-8 word academic search"}},
            {{"area": "what aspect this targets (within scope)", "priority": 4, "search_query": "3-8 word academic search"}},
            {{"area": "what aspect this targets (within scope)", "priority": 3, "search_query": "3-8 word academic search"}},
            {{"area": "what aspect this targets (within scope)", "priority": 2, "search_query": "3-8 word academic search"}},
            {{"area": "what aspect this targets (within scope)", "priority": 1, "search_query": "3-8 word academic search"}}
        ]
    }}
    
    QUERY-WRITING RULES:
    - Priority 5 is the MOST DIRECT query for the research question.
    - Each query must use the specific entities/concepts from the question itself.
    - Queries should be 3-8 words, written like you would type into PubMed.
    - Do NOT include dosages, ages, or other numeric specifics.
    - Use your knowledge of how real papers in this field are titled.
    - Each of the 5 queries must use substantively different terms."""

  question = HumanMessage(configuration.USER_PROMPT)
  system = SystemMessage(system_prompt)
  messages = [system, question]
  ### surround by try
  response = llm.invoke(messages)
  #print(response.content_blocks[0]['text'])
  response_json = json.loads(response.content_blocks[0]['text'])
  search_queries = []
  for focus in response_json['focus_areas']:
    search_queries.append(focus['search_query'])
  return search_queries

def main():

  print("Determining how to query the repositories.")
  search_queries = GenerateSearchQueries()

  print("\nSearching repositories using the following queries:")
  EstablishQueryTable()
  search_results = []
  for query in search_queries:
    print(f"  - {query}")
    existing_queries =\
      DatabaseFunctions.query_database(database_connection,
                                       query_records_table, "Query", query)
    if len(existing_queries) == 0:
      DatabaseFunctions.insert_record(database_connection, query_records_table, (query,))
      print("      Arxiv ", end = "")
      Arxiv = paper_discovery.ArxivClient()
      search_results.append(Arxiv.search(query))
      print("Crossref ", end="")
      Crossref = paper_discovery.CrossrefClient()
      search_results.append(Crossref.search(query))
      print("EuroPMC ", end="")
      EuropePMC = paper_discovery.EuropePMCClient()
      search_results.append(EuropePMC.search(query))
      print("OpenAlex ", end="")
      OpenAlex = paper_discovery.OpenAlexClient()
      search_results.append(OpenAlex.search(query))
      print()

  print("Adding search results to the database.")
  EstablishDocumentsTable()
  for result in search_results:
    for paper in result.papers:
      paper.title = remove_html_tags(paper.title)
      paper.title = paper.title.strip()
      if paper.title[- 1] == ".": paper.title = paper.title[:-1]
      if paper.title and paper.abstract and paper.open_access_pdf_url:
        paper.abstract = remove_html_tags(paper.abstract)
        paper.abstract = paper.abstract.strip()
        paper.open_access_pdf_url = paper.open_access_pdf_url.strip()
        DatabaseFunctions.insert_record(database_connection, document_records_table,
                                  (paper.title, paper.abstract, paper.open_access_pdf_url))

  print("Creating webpage containing search results.")
  document_records =\
    DatabaseFunctions.get_all_records(database_connection, document_records_table, "Title")
  query_records =\
    DatabaseFunctions.get_all_records(database_connection, query_records_table, "Query")
  with open(f"{configuration.DATABASE_DIRECTORY}/{configuration.WEBPAGE}", "w") as search_results_file:
    search_results_file.write(
"""
  <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
  <html xmlns="http://www.w3.org/1999/xhtml">
  <head>
  <meta content="IE=11.0000" http-equiv="X-UA-Compatible" />
  <meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1" />     
  <title>Topic-Specific Search Results</title>     
  <meta name="Keywords" content="Literature Review, Deep Research" />     
  <meta name="Description" content="AI=Generated search of open-access repositories of peer-reviewed papers and books." />     
  <meta name="author" content="GitHub Link" />     
  <link href="favicon.ico" rel="shortcut icon" type="image/x-icon" />
  <meta name="GENERATOR" content="MSHTML 11.00.9600.18125" />
  <meta name="google-site-verification" content="ZQnYGGLL9wivKvJXO5I8geX6Xt0IAHsFWGyvfuKMJJw" />
  
  <style type="text/css">
  <!--
  .StandardFont {
    font-family: Arial, Helvetica, sans-serif;
  }
  .SmallFont {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 9pt;
    font-style: normal;
    line-height: normal;
    font-weight: bold;
    font-variant: normal;
    text-transform: none;
    text-decoration: none;
  }
  .TitleFont {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 17pt;
    font-style: normal;
    line-height: normal;
    font-weight: bold;
    font-variant: normal;
    text-transform: none;
    color: #FC0;
    text-decoration: none;
  }
  td{
    padding: 5px 10px 0;
  }
  -->
  </style>
  </head>
  
  <body>
  <h1>Topic-Specific Search Results</h1>
  <p class="SmallFont">
  These are the search results from the following AI-generated queries<br>
  of open-access repositories of peer-reviewed papers and books.        
  </p>
  <p class="StandardFont"><b>Queries:</b></p>
  <p class="SmallFont">
  \n
"""
    )
    for record in query_records:
      search_results_file.write(record[0] + "<br>\n")
    search_results_file.write(
"""</p>
   <br><p class="StandardFont"><b>Documents:</b></p>
   <p class="SmallFont">\n
"""
    )
    for record in document_records:
      search_results_file.write('<br><div class="abstract">\n')
      search_results_file.write(f"<h4><b>{record[0].encode("ascii", "ignore").decode("ascii")}</b></h4>\n")
    search_results_file.write(f'<span class="text">{record[1].encode("ascii", "ignore").decode("ascii")}</span><br>\n')
    search_results_file.write(f'<a href="{record[2]}">{record[2]}</a></div><br><br>\n')
    search_results_file.write("</p>\n")
    search_results_file.write("\n</body>")

  print("Finished")
  DatabaseFunctions.close_connection(database_connection)
