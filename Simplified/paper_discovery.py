
import time
import hashlib
import re

import arxiv
import requests
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import quote as url_quote

email = "peter_raeth@juno.com"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PaperMetadata:
  title: str
  authors: List[str]
  year: Optional[int]
  abstract: Optional[str]
  doi: Optional[str]
  venue: Optional[str]
  citation_count: Optional[int]
  publication_types: List[str]
  open_access_pdf_url: Optional[str]
  source_api: str
  external_ids: Dict[str, str] = field(default_factory=dict)
  full_text_available: bool = False
  full_text_path: Optional[str] = None
  full_text_content: Optional[str] = None
  acquisition_method: Optional[str] = None
  acquisition_attempted: bool = False

  def __post_init__(self):
    if self.doi:
      self.paper_id = f"doi:{self.doi.lower().strip()}"
    else:
      title_hash = hashlib.md5(self.title.lower().strip().encode()).hexdigest()[:12]
      self.paper_id = f"hash:{title_hash}"

  def to_catalog_entry(self) -> Dict:
    return {
      "paper_id": self.paper_id, "title": self.title,
      "authors": self.authors[:3], "year": self.year,
      "venue": self.venue, "citation_count": self.citation_count,
      "doi": self.doi, "has_full_text": self.full_text_available,
      "abstract_preview": (self.abstract[:300] + "...") if self.abstract and len(self.abstract) > 300 else self.abstract,
      "source_api": self.source_api, "publication_types": self.publication_types,
    }


@dataclass
class SearchResult:
  query: str
  api_name: str
  papers_found: int
  papers: List[PaperMetadata]
  error: Optional[str] = None
  response_time: float = 0.0


@dataclass
class APIStats:
  total_queries: int = 0
  total_results: int = 0
  total_errors: int = 0
  total_full_texts: int = 0
  avg_response_time: float = 0.0
  last_error: Optional[str] = None

  @property
  def success_rate(self) -> float:
    if self.total_queries == 0:
      return 0.0
    return (self.total_queries - self.total_errors) / self.total_queries

  @property
  def avg_results_per_query(self) -> float:
    successful = self.total_queries - self.total_errors
    return self.total_results / successful if successful > 0 else 0.0

  def to_summary(self) -> str:
    return (f"queries={self.total_queries}, results={self.total_results}, "
            f"errors={self.total_errors}, full_texts={self.total_full_texts}, "
            f"success_rate={self.success_rate:.0%}, avg={self.avg_results_per_query:.1f}")


# =============================================================================
# API CLIENTS
# =============================================================================

class OpenAlexClient:
  def __init__(self):
    self.base_url = "https://api.openalex.org"
    self.email = _usable_email(email)
    self.results_per_page = 25
    self.max_pages = 3
    self.rate_limit_delay = 0.2

  def search(self, query: str) -> SearchResult:
    limit = self.results_per_page
    start_time = time.time()
    papers, error = [], None

    # Refine the query.
    start_date = None
    end_date = None
    index = query.rfind('(')
    if index >= 0:
      query_text = query[0 : index].strip()
      start_date = query[index + 1 : index + 5].strip()
      end_date = query[query.rfind(',') + 1 : query.rfind(')')].strip()
      query = f'{query_text}'
    #print(f"Searching OpenAllex for: '{query}' ...")

    try:
      total_to_fetch = min(limit, self.results_per_page * self.max_pages)
      page = 1
      while len(papers) < total_to_fetch:
        params = {"search": query, "per_page": min(self.results_per_page, total_to_fetch - len(papers)),
                  "page": page, "sort": "cited_by_count:desc",
                  "select": "id,doi,title,authorships,publication_year,primary_location,"
                            "cited_by_count,type,abstract_inverted_index,open_access,biblio"
                  }
        # Only sent when configured — an empty mailto is worse than none.
        if self.email: params["mailto"] = self.email
        if start_date and end_date:
          params["filter"] =\
            f"from_publication_date:{start_date}-01-01,to_publication_date:{end_date}-12-31"
        resp = requests.get(f"{self.base_url}/works", params=params, timeout=30)
        if resp.status_code != 200:
          error = f"HTTP {resp.status_code}: {resp.text[:200]}"
          break
        data = resp.json()
        results = data.get("results", [])
        if not results:
          break
        for item in results:
          p = self._parse(item)
          if p:
            papers.append(p)
        if page * self.results_per_page >= data.get("meta", {}).get("count", 0):
          break
        page += 1
        if len(papers) < total_to_fetch:
          time.sleep(self.rate_limit_delay)
    except requests.exceptions.Timeout:
      error = "Timed out"
    except requests.exceptions.ConnectionError:
      error = "Connection failed"
    except Exception as e:
      error = str(e)
    return SearchResult(query=query, api_name="openalex",
                        papers_found=len(papers), papers=papers,
                        error=error, response_time=time.time() - start_time)

  def lookup_by_doi(self, doi: str) -> Optional[PaperMetadata]:
    try:
      doi_clean = doi.replace("https://doi.org/", "")
      resp = requests.get(f"{self.base_url}/works/https://doi.org/{doi_clean}",
                          params=({"mailto": self.email} if self.email else {}),
                          timeout=15)
      if resp.status_code == 200:
        return self._parse(resp.json())
    except Exception:
      pass
    return None

  def _parse(self, item: Dict) -> Optional[PaperMetadata]:
    try:
      authors = [a.get("author", {}).get("display_name", "")
                 for a in item.get("authorships", [])
                 if a.get("author", {}).get("display_name")]
      doi_raw = item.get("doi", "") or ""
      doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None
      pdf_url = None
      oa_info = item.get("open_access") or {}
      pdf_url = oa_info.get("oa_url")
      if not pdf_url:
        primary_loc = item.get("primary_location") or {}
        if primary_loc.get("is_oa"):
          pdf_url = primary_loc.get("pdf_url") or primary_loc.get("landing_page_url")
      abstract = self._reconstruct_abstract(item.get("abstract_inverted_index"))
      venue = ""
      source = (item.get("primary_location") or {}).get("source") or {}
      venue = source.get("display_name", "")
      ext_ids = {}
      if doi:
        ext_ids["DOI"] = doi
      oa_id = item.get("id", "")
      if oa_id:
        ext_ids["OpenAlex"] = oa_id
      return PaperMetadata(
        title=item.get("title") or "Unknown", authors=authors,
        year=item.get("publication_year"), abstract=abstract, doi=doi,
        venue=venue, citation_count=item.get("cited_by_count"),
        publication_types=[item.get("type", "")] if item.get("type") else [],
        open_access_pdf_url=pdf_url, source_api="openalex", external_ids=ext_ids)
    except Exception as e:
      logger.debug(f"OpenAlex parse error: {e}")
      return None

  def _reconstruct_abstract(self, inv_idx: Optional[Dict]) -> Optional[str]:
    if not inv_idx:
      return None
    try:
      positions = []
      for word, posns in inv_idx.items():
        for p in posns:
          positions.append((p, word))
      positions.sort()
      return " ".join(w for _, w in positions)
    except Exception:
      return None


class EuropePMCClient:
  """Europe PMC — free, no auth, 10 req/s. Strong for biomedical + preprints."""
  def __init__(self):
    self.base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    self.results_per_page = 25
    self.max_pages = 3
    self.rate_limit_delay = 0.15

  def search(self, query: str) -> SearchResult:
    limit = self.results_per_page
    start_time = time.time()
    papers, error = [], None

    # Refine the query.
    index = query.rfind('(')
    if index >= 0:
      query_text = query[0 : index].strip()
      start_date = query[index + 1 : index + 5].strip()
      end_date = query[query.rfind(',') + 1 : query.rfind(')')].strip()
      query = f'{query_text} AND PUB_YEAR:[{start_date} TO {end_date}]'
    query += " AND OPEN_ACCESS:y"
    #print(f"Searching EuropePMC for: '{query}' ...")

    try:
      total_to_fetch = min(limit, self.results_per_page * self.max_pages)
      cursor_mark = "*"
      while len(papers) < total_to_fetch:
        params = {
          "query": query,
          "resultType": "core",
          "format": "json",
          "pageSize": min(self.results_per_page, total_to_fetch - len(papers)),
          "cursorMark": cursor_mark,
          "sort": "CITED desc",
        }
        resp = requests.get(f"{self.base_url}/search", params=params, timeout=30)
        if resp.status_code != 200:
          error = f"HTTP {resp.status_code}: {resp.text[:200]}"
          break
        data = resp.json()
        results = data.get("resultList", {}).get("result", [])
        if not results: break
        for item in results:
          p = self._parse(item)
          if p: papers.append(p)
        next_cursor = data.get("nextCursorMark")
        if not next_cursor or next_cursor == cursor_mark: break
        cursor_mark = next_cursor
        if len(papers) < total_to_fetch:
          time.sleep(self.rate_limit_delay)
    except requests.exceptions.Timeout:
      error = "Timed out"
    except requests.exceptions.ConnectionError:
      error = "Connection failed"
    except Exception as e:
      error = str(e)
    return SearchResult(query=query, api_name="europe_pmc",
                        papers_found=len(papers), papers=papers,
                        error=error, response_time=time.time() - start_time)

  def _parse(self, item: Dict) -> Optional[PaperMetadata]:
    try:
      authors = []
      author_list = item.get("authorList", {}).get("author", [])
      for a in author_list:
        name = a.get("fullName", "")
        if name:
          authors.append(name)
      doi = item.get("doi")
      pmid = item.get("pmid")
      pmcid = item.get("pmcid")
      pdf_url = None
      if item.get("isOpenAccess") == "Y" and pmcid:
        pdf_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
      venue = item.get("journalTitle", "")
      ext_ids = {}
      if doi:
        ext_ids["DOI"] = doi
      if pmid:
        ext_ids["PubMed"] = str(pmid)
      if pmcid:
        ext_ids["PubMedCentral"] = pmcid
      citation_count = item.get("citedByCount")
      abstract = item.get("abstractText")
      return PaperMetadata(
        title=item.get("title") or "Unknown", authors=authors,
        year=int(item.get("pubYear")) if item.get("pubYear") else None,
        abstract=abstract, doi=doi, venue=venue,
        citation_count=citation_count,
        publication_types=[item.get("pubType", "")] if item.get("pubType") else [],
        open_access_pdf_url=pdf_url, source_api="europe_pmc",
        external_ids=ext_ids)
    except Exception as e:
      logger.debug(f"Europe PMC parse error: {e}")
      return None


class CrossrefClient:
  """Crossref REST API — free, no auth, mailto for polite pool (10 req/s)."""
  def __init__(self):
    self.base_url = "https://api.crossref.org"
    self.email = email
    self.results_per_page = 20
    self.max_pages = 2
    self.rate_limit_delay = 0.15

  def search(self, query: str) -> SearchResult:
    limit = self.results_per_page
    start_time = time.time()
    papers, error = [], None

    # Refine the query.
    start_date = None
    end_date = None
    index = query.rfind('(')
    if index >= 0:
      query_text = query[0 : index].strip()
      start_date = query[index + 1 : index + 5].strip()
      end_date = query[query.rfind(',') + 1 : query.rfind(')')].strip()
      query = f'{query_text}'
    #print(f"Searching CrossRef for: '{query}' ...")

    try:
      total_to_fetch = min(limit, self.results_per_page * self.max_pages)
      offset = 0
      while offset < total_to_fetch:
        params = {
          "query": query,
          "rows": min(self.results_per_page, total_to_fetch - offset),
          "offset": offset,
          "sort": "relevance",
        }
        # Polite-pool identification, only when actually configured.
        if self.email: params["mailto"] = self.email
        if start_date and end_date:
          params["filter"] =\
            f"from-pub-date:{start_date},until-pub-date:{end_date}"
        ua = (f"AcademicLitReview/1.0 (mailto:{self.email})"
              if self.email else "AcademicLitReview/1.0")
        resp = requests.get(f"{self.base_url}/works", params=params, timeout=30,
                            headers={"User-Agent": ua})
        if resp.status_code == 429:
          time.sleep(5)
          resp = requests.get(f"{self.base_url}/works", params=params, timeout=30,
                              headers={"User-Agent": ua})
        if resp.status_code != 200:
          error = f"HTTP {resp.status_code}: {resp.text[:200]}"
          break
        data = resp.json()
        items = data.get("message", {}).get("items", [])
        if not items:
          break
        for item in items:
          p = self._parse(item)
          if p:
            papers.append(p)
        offset += len(items)
        total_results = data.get("message", {}).get("total-results", 0)
        if offset >= total_results:
          break
        if offset < total_to_fetch:
          time.sleep(self.rate_limit_delay)
    except requests.exceptions.Timeout:
      error = "Timed out"
    except requests.exceptions.ConnectionError:
      error = "Connection failed"
    except Exception as e:
      error = str(e)
    return SearchResult(query=query, api_name="crossref",
                        papers_found=len(papers), papers=papers,
                        error=error, response_time=time.time() - start_time)


  def _parse(self, item: Dict) -> Optional[PaperMetadata]:
    try:
      authors = []
      for a in item.get("author", []):
        given = a.get("given", "")
        family = a.get("family", "")
        name = f"{given} {family}".strip()
        if name:
          authors.append(name)
      doi = item.get("DOI")
      # Get title (Crossref returns as list)
      title_list = item.get("title", [])
      title = title_list[0] if title_list else "Unknown"
      # Year from published-print or published-online or created
      year = None
      for date_field in ["published-print", "published-online", "created"]:
        date_parts = item.get(date_field, {}).get("date-parts", [[]])
        if date_parts and date_parts[0] and date_parts[0][0]:
          year = date_parts[0][0]
          break
      # Venue
      venue_list = item.get("container-title", [])
      venue = venue_list[0] if venue_list else ""
      # Abstract (Crossref sometimes has it with JATS XML tags)
      abstract = item.get("abstract", "")
      if abstract:
        # Strip JATS XML tags
        abstract = re.sub(r'<[^>]+>', '', abstract).strip()
      # Citation count
      citation_count = item.get("is-referenced-by-count")
      # OA link
      pdf_url = None
      for link in item.get("link", []):
        if link.get("content-type") == "application/pdf":
          pdf_url = link.get("URL")
          break
      ext_ids = {}
      if doi:
        ext_ids["DOI"] = doi
      return PaperMetadata(
        title=title, authors=authors, year=year,
        abstract=abstract if abstract else None,
        doi=doi, venue=venue, citation_count=citation_count,
        publication_types=[item.get("type", "")] if item.get("type") else [],
        open_access_pdf_url=pdf_url, source_api="crossref",
        external_ids=ext_ids)
    except Exception as e:
      logger.debug(f"Crossref parse error: {e}")
      return None


class ArxivClient:

  # Arxiv API — free, no auth, mailto for polite pool (3 sec request delay).

  def __init__(self):
    self.base_url = "https://arxiv.org/search"
    self.email = _usable_email(email)
    self.results_per_page = 20
    self.max_pages = 2
    self.rate_limit_delay = 0.15

  def search(self, query: str) -> SearchResult:

    limit = self.results_per_page
    start_time = time.time()
    papers, error = [], None
    try: # this is where the retrieval takes place
      papers = self.search_arxiv(query)
    except Exception as e:
      error = str(e)

    return SearchResult(query=query, api_name="Arxiv",
                        papers_found=len(papers), papers=papers,
                        error=error, response_time=time.time() - start_time)

  def search_arxiv(self, query: str):

    # Search arXiv for papers associated with a query.
    # An alternative method for searching Arxiv is given in:
    # https://github.com/cywu92/PaperCrawler

    import arxiv
    import urllib.request

    # Create a custom User-Agent identifying your script name and email address.
    CUSTOM_USER_AGENT = f"MyResearchScript/1.0 (mailto:{self.email})"

    # Override the default URL opener globally for the current Python session.
    # Any request sent via the arxiv library carries the CUSTOM_USER_AGENT identity header.
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', CUSTOM_USER_AGENT)]
    urllib.request.install_opener(opener)

    # Initialize the arXiv client
    client = \
      arxiv.Client(page_size=self.results_per_page,  # max papers per page
                   delay_seconds=self.rate_limit_delay,  # seconds of delay between requests
                   num_retries=3  # max network retries
                   )

    # Refine the query.
    index = query.rfind('(')
    if index >= 0:
      query_text = query[0 : index].strip()
      start_date = query[index + 1 : index + 5].strip() + "01010000"
      end_date = query[query.rfind(',') + 1 : query.rfind(')')].strip() + "12312359"
      query = f'(ti:{query_text} OR abs:{query_text}) AND submittedDate:[{start_date} TO {end_date}]'
    #print(f"Searching Arxiv for: '{query}' ...")

    search =arxiv.Search(
      query=query,
      max_results=self.results_per_page,
      sort_by=arxiv.SortCriterion.Relevance
    )

    # Execute the search and process the results.
    search_results = []
    papers = []
    for result in client.results(search):
      # Clean the title to make a safe filename
      safe_title = "".join(c for c in result.title if c.isalnum() or c in (" ", "_", "-")).rstrip()
      result.title = safe_title
      search_results.append(result)
      #print(f"\nFound: {result.title}, ({result.published.year})")
      #print(f"PDF URL: {result.pdf_url}")
      # Format the result for later use.
      p = self._parse(result)
      if p: papers.append(p)

    return papers


  def _parse(self, item: arxiv.Result) -> Optional[PaperMetadata]:
    try:
      authors = [author.name for author in item.authors]
      doi = item.doi
      title = item.title
      year = item.published.year
      venue = item.journal_ref
      abstract = item.summary
      if abstract: # Strip JATS XML tags
        abstract = re.sub(r'<[^>]+>', '', abstract).strip()
      citation_count = None
      pdf_url = item.pdf_url
      ext_ids = {}
      if doi: ext_ids["DOI"] = doi
      return PaperMetadata(
        title=title, authors=authors, year=year,
        abstract=abstract if abstract else None,
        doi=doi, venue=venue, citation_count=citation_count,
        publication_types=[],
        open_access_pdf_url=pdf_url, source_api="arxiv",
        external_ids=ext_ids)
    except Exception as e:
      logger.debug(f"Arxiv parse error: {e}")
      return None


def _usable_email(value: Optional[str]) -> str:
  """Return a contact email only if it is actually usable, else "".

  The bundled config ships EMPTY email defaults so no maintainer's address is
  committed to source control. An empty (or placeholder) address must never be
  sent to an API: Unpaywall rejects the request outright, and OpenAlex /
  Crossref would receive a meaningless `mailto=` that forfeits polite-pool
  access without saying why. Every consumer routes through this so the "no
  email configured" case is handled in one place.
  """
  if not value:
    return ""
  v = str(value).strip()
  if not v or "@" not in v or "example.com" in v.lower():
    return ""
  return v


class UnpaywallClient:
  def __init__(self):
    self.base_url = "https://api.unpaywall.org/v2"
    self.email = _usable_email(email)
    self.rate_limit_delay = 0.1
    # Unpaywall REQUIRES a real address. An unset or placeholder value used
    # to slip through the old "example.com" test (an empty string contains
    # no "example.com"), so every lookup failed at the API with no
    # explanation. Anything not usable is now caught here, up front.
    self._email_valid = bool(self.email)
    if not self._email_valid:
      print("Unpaywall: no valid email configured — "
            f"full-text lookups will be skipped.")
      print("Fix: export UNPAYWALL_EMAIL=\"your.real@email.com\"")

  def find_open_access(self, doi: str) -> Dict:
    result = {"pdf_url": None, "all_locations": [], "is_oa": False, "error": ""}
    if not doi:
      result["error"] = "No DOI"
      return result
    if not self._email_valid:
      result["error"] = "Set UNPAYWALL_EMAIL env var to a real email"
      return result
    try:
      doi_clean = doi.strip().replace("https://doi.org/", "").replace("http://doi.org/", "")
      doi_encoded = url_quote(doi_clean, safe='')
      resp = requests.get(f"{self.base_url}/{doi_encoded}",
                          params={"email": self.email}, timeout=15)
      if resp.status_code == 404:
        result["error"] = "DOI not in Unpaywall"
        return result
      if resp.status_code != 200:
        result["error"] = f"HTTP {resp.status_code}"
        return result
      data = resp.json()
      result["is_oa"] = data.get("is_oa", False)
      best = data.get("best_oa_location") or {}
      if best:
        result["pdf_url"] = best.get("url_for_pdf") or best.get("url")
      for loc in data.get("oa_locations", []):
        result["all_locations"].append({
          "url": loc.get("url"), "pdf_url": loc.get("url_for_pdf"),
          "host_type": loc.get("host_type"), "version": loc.get("version")})
      time.sleep(self.rate_limit_delay)
    except requests.exceptions.Timeout:
      result["error"] = "Timed out"
    except Exception as e:
      result["error"] = str(e)
    return result
