import csv
import time
import logging
import os
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.common.exceptions import StaleElementReferenceException, InvalidSessionIdException
from field_detector import FieldDetector
from form_analyzer import FormAnalyzer

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("form_scraper.log"), 
                              logging.StreamHandler()])
logger = logging.getLogger(__name__)

class FormFieldScraper:
    def __init__(self, headless=True, timeout=30):
        """Initialize the scraper with browser options"""
        self.timeout = timeout
        self.headless = headless
        self.setup_browser()
        
        # Initialize helpers
        self.field_detector = FieldDetector()
        
    def setup_browser(self):
        """Set up a new browser instance"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36")
        
        # Add options to avoid detection
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        # Store options for recreation if needed
        self.chrome_options = chrome_options
        
        # Create new browser
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Initialize form analyzer with the new driver
        self.form_analyzer = FormAnalyzer(self.driver)
        
    def reset_browser(self):
        """Reset the browser when session becomes invalid"""
        logger.info("Resetting browser session")
        try:
            self.driver.quit()
        except:
            pass
        self.setup_browser()
        
    def __del__(self):
        """Clean up resources"""
        try:
            self.driver.quit()
        except:
            pass
    
    def scrape_form_fields(self, url, retry_count=0, max_retries=2):
        """Extract all form fields from a URL, with retry mechanism for session errors"""
        logger.info(f"Processing: {url}")
        result = {
            'url': url,
            'domain': urlparse(url).netloc,
            'fields': {},
            'additional_fields': [],
            'has_captcha': False,
            'has_additional_required_fields': False,
            'error': None
        }
        
        # Initialize all standard fields as empty
        for field in self.field_detector.standard_fields:
            result['fields'][field] = {'xpath': '', 'type': '', 'required': False, 'found': False}
        
        try:
            self.driver.get(url)
            try:
                WebDriverWait(self.driver, self.timeout).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                result['error'] = "Timeout loading page"
                return result
            
            # Check for CAPTCHA but continue processing anyway
            try:
                has_captcha = self.form_analyzer.has_captcha() 
                result['has_captcha'] = has_captcha
                if has_captcha:
                    logger.info(f"CAPTCHA detected on {url} - continuing to extract fields anyway")
            except Exception as e:
                logger.warning(f"Error checking for CAPTCHA: {str(e)}")
            
            # Get all form elements
            main_container, all_form_elements = self.form_analyzer.find_form_and_elements()
            
            if not main_container:
                result['error'] = "No form or input fields found"
                return result
                
            if len(all_form_elements) < 2:
                result['error'] = "Not enough form elements found"
                return result
            
            # Process all fields
            self.process_form_elements(all_form_elements, result)
            
            # Set flag if additional required fields were found
            if result['additional_fields']:
                result['has_additional_required_fields'] = True
            
        except InvalidSessionIdException as e:
            logger.warning(f"Invalid session ID encountered: {str(e)}")
            if retry_count < max_retries:
                logger.info(f"Retrying URL (attempt {retry_count+1}/{max_retries}): {url}")
                self.reset_browser()
                return self.scrape_form_fields(url, retry_count+1, max_retries)
            else:
                result['error'] = f"Invalid session ID after {max_retries} retries"
        except TimeoutException:
            result['error'] = "Timeout loading page"
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error processing {url}: {str(e)}")
            # If the error looks like a browser issue, try to recover
            if "session" in str(e).lower() or "browser" in str(e).lower():
                if retry_count < max_retries:
                    logger.info(f"Retrying URL (attempt {retry_count+1}/{max_retries}): {url}")
                    self.reset_browser()
                    return self.scrape_form_fields(url, retry_count+1, max_retries)
        
        return result

    def process_form_elements(self, elements, result):
        """
        Process form elements with enhanced detection
        
        Args:
            elements (list): Web elements to process
            result (dict): Result dictionary to update
        
        Returns:
            None: Updates result in-place
        """
        # Tracking variables for smart detection
        processed_fields = set()
        
        # Enhanced candidate tracking
        privacy_candidates = []
        email_confirmation_candidates = []
        
        # First pass: Primary field detection
        try:
            # Validate input
            if not elements:
                logger.warning("No elements found to process")
                return
            
            for element in elements:
                try:
                    # Skip if element is invalid
                    if not self.form_analyzer.is_element_visible(element):
                        continue
                    
                    element_type = element.get_attribute("type") or element.tag_name
                    
                    # Skip hidden inputs
                    if element_type == 'hidden':
                        continue
                    
                    # Special handling for submit buttons
                    if element_type in ['submit', 'button', 'image']:
                        self.form_analyzer.process_button(element, result)
                        continue
                    
                    guessed_name = self.field_detector.guess_field_name(element, self.driver)
                    mapped_field = self.field_detector.map_to_standard_field(guessed_name, element_type)
                    
                    # Detect required status
                    is_required = self.form_analyzer.is_element_required(element)
                    
                    # Collect privacy policy candidates
                    if element_type in ['checkbox', 'radio']:
                        privacy_terms = ["privacy", "terms", "policy", "agree", "consent", "gdpr"]
                        if any(term in guessed_name.lower() for term in privacy_terms):
                            privacy_candidates.append((element, guessed_name))
                    
                    # Collect email confirmation candidates
                    if (mapped_field == 'ConfirmEmail' or 
                        (element_type == 'email' and 
                        any(term in guessed_name.lower() for term in ['confirm', 'verify', 'repeat']))):
                        email_confirmation_candidates.append((element, guessed_name))
                    
                    # Map primary fields
                    if mapped_field and mapped_field not in processed_fields:
                        result['fields'][mapped_field] = {
                            'xpath': self.form_analyzer.get_xpath(element),
                            'type': element_type,
                            'required': is_required,
                            'found': True
                        }
                        processed_fields.add(mapped_field)
                    elif is_required:
                        # Capture required additional fields
                        result['additional_fields'].append({
                            'field_name': guessed_name,
                            'xpath': self.form_analyzer.get_xpath(element),
                            'element_type': element_type,
                            'required': True
                        })
                    
                    # Capture non-required additional fields
                    elif not mapped_field:
                        result['additional_fields'].append({
                            'field_name': guessed_name,
                            'xpath': self.form_analyzer.get_xpath(element),
                            'element_type': element_type,
                            'required': False
                        })
                
                except Exception as e:
                    logger.debug(f"Individual element processing error: {e}")
            
            # Add privacy field if not found
            if privacy_candidates and not result['fields']['Privacy']['found']:
                best_privacy = privacy_candidates[0][0]
                result['fields']['Privacy'] = {
                    'xpath': self.form_analyzer.get_xpath(best_privacy),
                    'type': best_privacy.get_attribute("type"),
                    'required': False,
                    'found': True
                }
            
            # Add email confirmation field if not found
            if email_confirmation_candidates and not result['fields']['ConfirmEmail']['found']:
                best_confirm = email_confirmation_candidates[0][0]
                result['fields']['ConfirmEmail'] = {
                    'xpath': self.form_analyzer.get_xpath(best_confirm),
                    'type': best_confirm.get_attribute("type"),
                    'required': False,
                    'found': True
                }
            
            # Ensure submit button is found
            if not result['fields']['Submit']['found']:
                submit_buttons = self.form_analyzer.find_submit_buttons()
                if submit_buttons:
                    try:
                        element_type = submit_buttons[0].get_attribute("type") or "button"
                        result['fields']['Submit'] = {
                            'xpath': self.form_analyzer.get_xpath(submit_buttons[0]),
                            'type': element_type,
                            'required': True,
                            'found': True
                        }
                    except:
                        pass
            
            # Additional pass to find missing priority fields
            self.find_missing_fields(elements, result)
        
        except Exception as e:
            logger.error(f"Comprehensive field processing error: {e}")
            # Ensure minimal result structure if processing fails
            if 'Submit' not in result['fields']:
                result['fields']['Submit'] = {
                    'xpath': '',
                    'type': '',
                    'required': False,
                    'found': False
                } 

    def find_missing_fields(self, elements, result):
        """Find any important fields that weren't identified in the first pass"""
        # Look for privacy checkbox
        if not result['fields']['Privacy']['found']:
            privacy_element = self.form_analyzer.find_privacy_checkbox(elements)
            if privacy_element:
                try:
                    element_type = privacy_element.get_attribute("type") or privacy_element.tag_name
                    result['fields']['Privacy'] = {
                        'xpath': self.form_analyzer.get_xpath(privacy_element),
                        'type': element_type,
                        'required': self.form_analyzer.is_element_required(privacy_element),
                        'found': True
                    }
                except:
                    pass
        
        # Look for priority fields
        for field_name in self.field_detector.priority_fields:
            if not result['fields'][field_name]['found']:
                candidate = self.form_analyzer.find_best_candidate_for_field(
                    elements, field_name, self.field_detector)
                if candidate:
                    try:
                        element_type = candidate.get_attribute("type") or candidate.tag_name
                        result['fields'][field_name] = {
                            'xpath': self.form_analyzer.get_xpath(candidate),
                            'type': element_type,
                            'required': self.form_analyzer.is_element_required(candidate),
                            'found': True
                        }
                    except:
                        pass
        
        # Special case for email fields
        if not result['fields']['Email']['found'] and result['fields']['ConfirmEmail']['found']:
            result['fields']['Email'] = result['fields']['ConfirmEmail']
            result['fields']['ConfirmEmail'] = {'xpath': '', 'type': '', 'required': False, 'found': False}
    
    def process_url_list(self, url_list, output_file="form_fields.csv", batch_size=20):
        """Process a list of URLs and save results to CSV with checkpointing and batching"""
        all_results = []
        completed_urls = set()
        
        # Check for existing checkpoint file
        checkpoint_file = f"{output_file}.checkpoint"
        if os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, 'r') as f:
                    for line in f:
                        completed_urls.add(line.strip())
                logger.info(f"Loaded {len(completed_urls)} completed URLs from checkpoint")
            except Exception as e:
                logger.warning(f"Error loading checkpoint file: {str(e)}")
        
        # Filter out already completed URLs
        urls_to_process = [url for url in url_list if url not in completed_urls]
        logger.info(f"Processing {len(urls_to_process)} URLs out of {len(url_list)} total")
        
        # Process URLs in batches
        for i in range(0, len(urls_to_process), batch_size):
            batch_urls = urls_to_process[i:i+batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(urls_to_process)-1)//batch_size + 1} ({len(batch_urls)} URLs)")
            
            batch_results = []
            for j, url in enumerate(batch_urls):
                try:
                    logger.info(f"Processing URL {i+j+1}/{len(urls_to_process)}: {url}")
                    result = self.scrape_form_fields(url)
                    batch_results.append(result)
                    
                    # Update checkpoint after each successful URL
                    try:
                        with open(checkpoint_file, 'a') as f:
                            f.write(f"{url}\n")
                    except Exception as e:
                        logger.warning(f"Error updating checkpoint: {str(e)}")
                    
                    # Small delay to be nice to servers
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Unrecoverable error processing {url}: {str(e)}")
                    
                    # Add error entry to results
                    error_result = {
                        'url': url,
                        'domain': urlparse(url).netloc if url.startswith('http') else '',
                        'fields': {field: {'xpath': '', 'type': '', 'required': False, 'found': False} 
                                  for field in self.field_detector.standard_fields},
                        'additional_fields': [],
                        'has_captcha': False,
                        'has_additional_required_fields': False,
                        'error': str(e)
                    }
                    batch_results.append(error_result)
            
            # Add batch results to all results
            all_results.extend(batch_results)
            
            # Save interim results after each batch
            self.save_results_to_csv(all_results, output_file)
            
            # Reset browser between batches to prevent memory issues
            if i + batch_size < len(urls_to_process):
                logger.info("Resetting browser between batches")
                self.reset_browser()
        
        # Save final results
        self.save_results_to_csv(all_results, output_file)
        logger.info(f"All results saved to {output_file}")
        
        return all_results
        
    def save_results_to_csv(self, results, output_file):
        """Save the scraped results to a CSV file"""
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            # Prepare field names for CSV
            fieldnames = ['url', 'domain']
            
            # Add field type and xpath columns
            for field in self.field_detector.standard_fields:
                fieldnames.append(f"{field}Type")
                fieldnames.append(f"{field}XPath")
            
            # Add columns for additional fields and flags
            # We'll handle additional fields separately since they're dynamic
            fieldnames.extend([
                'HasAdditionalFields', 
                'HasCaptcha', 
                'error'
            ])
            
            # Count maximum number of additional fields in any result
            max_additional = 0
            for result in results:
                if len(result.get('additional_fields', [])) > max_additional:
                    max_additional = len(result.get('additional_fields', []))
            
            # Add columns for each potential additional field
            for i in range(1, max_additional + 1):
                fieldnames.append(f"AdditionalField{i}Name")
                fieldnames.append(f"AdditionalField{i}Type")
                fieldnames.append(f"AdditionalField{i}XPath")
                fieldnames.append(f"AdditionalField{i}Required")
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                row = {
                    'url': result['url'],
                    'domain': result['domain'],
                    'HasAdditionalFields': len(result.get('additional_fields', [])) > 0,
                    'HasCaptcha': result.get('has_captcha', False),
                    'error': result.get('error', '')
                }
                
                # Add standard fields
                for field_name, field_data in result['fields'].items():
                    row[f"{field_name}XPath"] = field_data.get('xpath', '') if field_data.get('found', False) else ""
                    row[f"{field_name}Type"] = field_data.get('type', '') if field_data.get('found', False) else ""
                
                # Add all additional fields with numbering
                additional_fields = result.get('additional_fields', [])
                for i, field in enumerate(additional_fields, 1):
                    if i <= max_additional:  # Only add up to the max count we determined
                        row[f"AdditionalField{i}Name"] = field.get('field_name', '')
                        row[f"AdditionalField{i}Type"] = field.get('element_type', '')
                        row[f"AdditionalField{i}XPath"] = field.get('xpath', '')
                        row[f"AdditionalField{i}Required"] = field.get('required', False)
                
                writer.writerow(row)