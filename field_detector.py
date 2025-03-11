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
            
            "FirstName": ["first name", "firstname", "given name", "forename", "first", "fname", "givenname"],
            
            "LastName": ["last name", "lastname", "surname", "family name", "last", "lname", "familyname"],
            
            "Email": ["email", "e-mail", "mail", "emailaddress", "e mail"],
            
            "ConfirmEmail": ["confirm email", "repeat email", "verify email", "email confirm", "reenter email"],
            
            "JobTitle": ["job title", "position", "role", "job role", "job position", "occupation", "title", "jobtitle"],
            
            "Organization": ["company", "organization", "organisation", "employer", "business", "firm", "workplace"],
            
            "Phone": ["phone", "telephone", "mobile", "cell", "contact number", "phonenumber", "tel"],
            
            "Street": ["street", "address", "address line", "street address", "road", "addressline1", "address1"],
            
            "City": ["city", "town", "locality", "municipality"],
            
            "State": ["state", "province", "region", "county", "territory"],
            
            "Zipcode": ["zip", "zipcode", "postal code", "post code", "zip code", "postalcode", "postcode"],
            
            "Country": ["country", "nation"],
            
            "Privacy": ["privacy", "terms", "consent", "agree", "accept", "policy", "opt in", "gdpr", "marketing"]
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
            
            # Special handling for privacy checkboxes/radios
            if element_type in ['checkbox', 'radio']:
                terms_patterns = self.field_patterns["Privacy"]
                for pattern in terms_patterns:
                    if pattern in guessed_name:
                        return "Privacy"
            
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
        except Exception as e:
            logger.debug(f"Error in map_to_standard_field: {str(e)}")
                    
        # Return None if no match found
        return None