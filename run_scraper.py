# run_scraper.py
import logging
import sys
from form_scraper import FormFieldScraper

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("form_scraper.log"), 
                              logging.StreamHandler()])
logger = logging.getLogger(__name__)

def load_urls_from_file(file_path):
    """Load URLs from a text file (one URL per line)"""
    urls = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                url = line.strip()
                if url and not url.startswith('#'):  # Skip empty lines and comments
                    urls.append(url)
        logger.info(f"Loaded {len(urls)} URLs from {file_path}")
        return urls
    except Exception as e:
        logger.error(f"Error loading URLs from file: {str(e)}")
        return []

if __name__ == "__main__":
    # Hardcoded configuration
    url_file = "urls.txt"  # Your URLs file
    output_file = "form_fields_new.csv"  # Output CSV file
    batch_size = 20  # URLs per batch
    timeout = 30  # Page load timeout in seconds
    headless = True  # Set to False to see the browser window
    
    # Load URLs from file
    urls = load_urls_from_file(url_file)

    if not urls:
        logger.error("No URLs loaded. Please check your URL file.")
        sys.exit(1)

    try:
        # Create and run the scraper
        scraper = FormFieldScraper(headless=headless, timeout=timeout)
        results = scraper.process_url_list(
            urls, 
            output_file=output_file,
            batch_size=batch_size
        )

        # Print a summary of results
        total = len(results)
        captchas = sum(1 for r in results if r.get('has_captcha', False))
        with_additional = sum(1 for r in results if r.get('additional_fields', []))
        errors = sum(1 for r in results if r.get('error', None))

        print("\n" + "="*50)
        print("SCRAPING SUMMARY")
        print("="*50)
        print(f"Total URLs processed: {total}")
        print(f"Forms with CAPTCHAs: {captchas}")
        print(f"Forms with additional fields: {with_additional}")
        print(f"Errors encountered: {errors}")
        print(f"Results saved to: {output_file}")
        print("="*50)
        
    except KeyboardInterrupt:
        print("\nOperation interrupted by user. Partial results saved.")
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        sys.exit(1)