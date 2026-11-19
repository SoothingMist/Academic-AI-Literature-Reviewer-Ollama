
# This Python script searches various open-access repositories
# of papers, books, and dissertations. It downloads and summarizes their abstracts.
# A report is generated on an overall summarization and a summarization of each abstract

# This code is designed for batch runs. See configuration.py to set the user prompt
# and other parameters.

import SearchDownload
import SummarizeAbstracts
import time

# Begins the necessary chain of events.
if __name__ == '__main__':
    start = time.perf_counter()
    SearchDownload.main()
    SummarizeAbstracts.main()
    end = time.perf_counter()
    print(f"Elapsed time: {((end - start)/60.0)/60:.1f} hours")
    exit(0)
