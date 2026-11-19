
"""
  Developed and tested this application on the following computer.
  It is a low-end machine, relative to this type of application.
    Dell Alienware Aurora R9
    OS:  Windows 11 - Fully Updated - 64Bit x64
    CPU: Intel Core i9-9900K 3.60GHz
    RAM: 32GB
    GPU: NVIDIA GeForce RTX 2060 6GB VRAM
"""
MODEL = 'qwen3:latest' # 5.2GB model, chokes on abstract 106/300, BATCH_SIZE = 500.
                       # Succeeded with BATCH_SIZE = 100.
                       # Run too several hours.

# Models that failed to perform:
#MODEL = 'qwen2.5:3b' # fails to generate good json
#MODEL = 'TinyLlama:latest' # fails to generate good json
#MODEL = 'Gemma3:1b' # fails to generate good json
#MODEL = 'phi4-mini:latest' # fails to follow user and system prompts
#MODEL = 'gemma3:4b' # fails to generate good json
#MODEL = 'llama3:latest' # fails to generate good json

BASE_OLLAMA_URL = "http://localhost:11434"
TEMPERATURE = 0.0
DATABASE_DIRECTORY = "./Database"
WEBPAGE = "search_results.html"
BATCH_SIZE = 100 # number of abstracts to analyze at a time

USER_PROMPT = \
  """Question: What are ways to detect "fall armyworm" early?
     Instructions:
       - Restrict paper retrieval dates to the years 2023 through 2026 inclusive.
       - Wherever "fall armyworm" appears, "fall armyworm" must be maintained as a quoted phrase
         using straight quotation marks (").
       - Attach the retrieval date range to the end of each search query by using this format:
         "(start year , end year)"
  """
