import re
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException
import logging

logger = logging.getLogger(__name__)

class FieldDetector:
    def __init__(self):
        # Define standard fields we're looking for
        self.standard_fields = [
            "Title", "FirstName", "LastName", "Email", "ConfirmEmail", 
            "JobTitle", "Organization", "Phone", "Street", "City",
            "State", "Zipcode", "Country", "Privacy", "Submit"
        ]
        
        # Priority fields that must be returned if possible
        self.priority_fields = ["FirstName", "LastName", "Email"]
        
        # Define patterns to match field names to standard fields
        self.field_patterns = {
            "Title": ["title", "prefix", "salutation", "honorific", "mr", "mrs", "ms", "dr", "prof", "suffix"],
            
            "FirstName": ["first name", "firstname", "given name", "forename", "first", "fname", "givenname", 
                         "name.*first", "first.*name", "given", "name_first"],
            
            "LastName": ["last name", "lastname", "surname", "family name", "last", "lname", "familyname", 
                        "name.*last", "last.*name", "family", "name_last", "sur name"],
            
            "Email": ["email", "e-mail", "mail", "emailaddress", "e mail", "your email", "primary email", 
                     "contact email", "email.*address", "address.*email"],
            
            "ConfirmEmail": ["confirm email", "repeat email", "verify email", "email confirm", "reenter email", 
                            "confirm.*email", "email.*confirm", "email.*again", "retype.*email", "verify.*email"],
            
            "JobTitle": ["job title", "position", "role", "job role", "job position", "occupation", "title", "jobtitle", 
                         "job_title", "job-title", "job function", "profession", "work title"],
            
            "Organization": ["company", "organization", "organisation", "employer", "business", "firm", "workplace", 
                            "company name", "employer name", "business name", "organization name", "institution", "Company Type" 
                            "corporation", "agency", "department", "employer info"],
            
            "Phone": ["phone", "telephone", "mobile", "cell", "contact number", "phonenumber", "tel", 
                      "phone.*number", "mobile.*number", "contact.*phone", "daytime phone", "evening phone", 
                      "cell.*number", "primary phone", "work phone", "home phone"],
            
            "Street": ["street", "address", "address line", "street address", "road", "addressline1", "address1", 
                      "addr1", "address line 1", "street name", "house number", "building", "apartment", 
                      "street.*address", "address.*line.*1", "addr.*line1", "address.*street", "shipping address", 
                      "billing address", "mailing address", "delivery address", "residence", "location"],
            
            "City": ["city", "town", "locality", "municipality", "urban area", "township", "city/town", 
                     "city name", "place", "village", "borough", "location.*city", "city.*location", "address.*city"],
            
            "State": ["state", "province", "region", "county", "territory", "division", "district", 
                      "state/province", "administrative area", "location.*state", "state.*region", 
                      "region.*state", "area"],
            
            "Zipcode": ["zip", "zipcode", "postal code", "post code", "zip code", "postalcode", "postcode", 
                        "postal", "pin code", "pin", "code postal", "zipcode.*postal", "postal.*zip", 
                        "zip.*code", "postal.*code", "area code"],
            
            "Country": ["country", "nation", "land", "territory", "nationality", "national", "country name", 
                        "country/region", "region/country", "location.*country", "country.*location"],
            
            "Privacy": ["privacy", "terms", "consent", "agree", "accept", "policy", "opt in", "gdpr", "marketing", 
                        "permission", "subscribe", "newsletter", "communications", "contact me", "contact you", 
                        "send me", "send you", "preference", "privacy.*policy", "terms.*conditions", 
                        "terms.*service", "cookie", "data policy", "personal data", "personal information", 
                        "data.*collect", "process.*data", "agreement", "updates", "notifications", "legal"]
        }
    
    def guess_field_name(self, element, driver):
        """Try to determine what the field is for based on attributes and nearby text - with error handling"""
        field_hints = []
        
        # Check various attributes for clues
        for attr in ['name', 'id', 'placeholder', 'aria-label', 'title', 'data-label']:
            try:
                value = element.get_attribute(attr)
                if value:
                    # Clean up the value to make it more readable
                    value = re.sub(r'[-_]', ' ', value).strip().lower()
                    if value and len(value) > 1:  # Skip single character or empty values
                        field_hints.append(value)
            except Exception as e:
                logger.debug(f"Error getting attribute {attr}: {str(e)}")
        
        # Check for associated label by for attribute
        try:
            label_id = element.get_attribute('id')
            if label_id:
                try:
                    labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{label_id}']")
                    for label in labels:
                        try:
                            field_hints.append(label.text.strip().lower())
                        except:
                            pass
                except:
                    pass
        except:
            pass
        
        # Check for parent label
        try:
            parent = element.find_element(By.XPATH, "./..")
            if parent.tag_name == 'label':
                field_hints.append(parent.text.strip().lower())
        except (NoSuchElementException, StaleElementReferenceException):
            pass
        except Exception as e:
            logger.debug(f"Error checking parent label: {str(e)}")
        
        # Look for preceding siblings with label-like content
        try:
            prev_elements = element.find_elements(By.XPATH, "./preceding-sibling::*")
            for prev in prev_elements:
                try:
                    if prev.tag_name in ['label', 'span', 'div', 'p']:
                        text = prev.text.strip().lower()
                        if text and len(text) < 50:  # Only consider short texts
                            field_hints.append(text)
                except (StaleElementReferenceException, AttributeError):
                    continue
                except Exception as e:
                    logger.debug(f"Error checking preceding siblings: {str(e)}")
        except:
            pass
        
        # NEW: Check for common address field container classes
        try:
            address_containers = [
                ".//ancestor::div[contains(@class, 'address')]",
                ".//ancestor::div[contains(@class, 'shipping')]",
                ".//ancestor::div[contains(@class, 'billing')]",
                ".//ancestor::fieldset[contains(.//legend, 'address')]"
            ]
            
            for xpath in address_containers:
                try:
                    container = element.find_element(By.XPATH, xpath)
                    if container:
                        # Try to get field section name if it's an address field
                        section_hints = []
                        try:
                            # Check if there are hints in legends or section headers
                            headers = container.find_elements(By.XPATH, ".//legend | .//h3 | .//h4 | .//label[contains(@class, 'heading')]")
                            for header in headers:
                                if header.text.strip():
                                    section_hints.append(header.text.strip().lower())
                        except:
                            pass
                        
                        # Add address hint if we found a container
                        field_hints.append("address field")
                        if section_hints:
                            field_hints.extend(section_hints)
                        break
                except:
                    continue
        except:
            pass
        
        # NEW: Check for label text after the element (for address fields sometimes)
        try:
            next_elements = element.find_elements(By.XPATH, "./following-sibling::*")
            for next_elem in next_elements[:2]:  # Only check the next 2 elements
                try:
                    if next_elem.tag_name in ['label', 'span', 'div', 'p']:
                        text = next_elem.text.strip().lower()
                        if text and len(text) < 50:
                            field_hints.append(text)
                except:
                    continue
        except:
            pass
        
        # Filter out empty strings and duplicates
        field_hints = [h for h in field_hints if h and not h.isspace()]
        
        # Remove duplicates while preserving order
        seen = set()
        field_hints = [h for h in field_hints if not (h in seen or seen.add(h))]
        
        # Join all hints
        if field_hints:
            return " ".join(field_hints)
        
        return "Unknown Field"
    
    def map_to_standard_field(self, guessed_name, element_type):
        """Map a guessed field name to one of our standard field names - with error handling"""
        if not guessed_name:
            return None
            
        try:
            guessed_name = guessed_name.lower()
            
            # Enhanced privacy checkbox detection
            if element_type in ['checkbox', 'radio']:
                privacy_patterns = self.field_patterns["Privacy"]
                
                # Special enhanced check for address type fields
                for pattern in privacy_patterns:
                    if pattern in guessed_name:
                        return "Privacy"
                        
                # Additional checks for common privacy consent patterns
                privacy_indicators = [
                    "i agree", "agree to", "accept", "consent", 
                    "subscribe", "sign up", "opt in", "permission",
                    "can contact", "may contact", "receive"
                ]
                
                for indicator in privacy_indicators:
                    if indicator in guessed_name:
                        return "Privacy"
            
            # Enhanced address field detection
            address_type_indicators = {
                "Street": ["address line", "street address", "address1", "billing address", "shipping address"],
                "City": ["city", "town"],
                "State": ["state", "province", "region"],
                "Zipcode": ["zip", "postal", "post code"],
                "Country": ["country", "nation"]
            }
            
            # Check each address type first with more specific patterns
            for field, indicators in address_type_indicators.items():
                for indicator in indicators:
                    if indicator in guessed_name:
                        return field
            
            # Check input type for email fields
            if element_type == 'email':
                # If it's the second email field on the page, it's likely confirmation
                if "confirm" in guessed_name or "verify" in guessed_name or "repeat" in guessed_name:
                    return "ConfirmEmail"
                return "Email"
                
            # Check input type for tel fields
            if element_type == 'tel':
                return "Phone"
                
            # Check for submit buttons
            if element_type in ['submit', 'button']:
                button_text = guessed_name.lower()
                if any(term in button_text for term in ["submit", "send", "continue", "next", "go", "register"]):
                    return "Submit"
            
            # Check each standard field pattern
            for std_field, patterns in self.field_patterns.items():
                for pattern in patterns:
                    try:
                        # Use regex to catch partial and word boundary matches
                        if re.search(r'\b' + re.escape(pattern) + r'\b', guessed_name):
                            return std_field
                        if pattern in guessed_name:
                            return std_field
                    except re.error:
                        # Handle regex errors
                        logger.debug(f"Regex error with pattern {pattern}")
                        if pattern in guessed_name:
                            return std_field
        
            # NEW: Handle address fields with common name/id patterns
            address_patterns = {
                "Street": ["addr", "address1", "line1", "street", "thoroughfare"],
                "City": ["city", "town", "locality"],
                "State": ["state", "province", "region", "territory"],
                "Zipcode": ["zip", "postal", "postcode", "postalcode"],
                "Country": ["country", "nation", "countries"]
            }
            
            for field, patterns in address_patterns.items():
                for pattern in patterns:
                    if pattern in guessed_name:
                        return field
                        
        except Exception as e:
            logger.debug(f"Error in map_to_standard_field: {str(e)}")
                    
        # Return None if no match found
        return None