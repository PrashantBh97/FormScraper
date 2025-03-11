from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException, JavascriptException
import logging
import re

logger = logging.getLogger(__name__)

class FormAnalyzer:
    def __init__(self, driver):
        self.driver = driver
    
    def has_captcha(self):
        """
        Comprehensive detection of all CAPTCHA types including:
        - reCAPTCHA/hCAPTCHA "I am not a robot"
        - Image recognition CAPTCHAs
        - Text-based CAPTCHA challenges
        """
        try:
            # 1. Check for reCAPTCHA and hCAPTCHA elements
            recaptcha_selectors = [
                "iframe[src*='recaptcha']",
                "iframe[src*='hcaptcha']",
                "div.g-recaptcha",
                "div[data-sitekey]",  
                "div.h-captcha",
                "[class*='turnstile']"
            ]
            
            for selector in recaptcha_selectors:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    return True
                    
            # 2. Check for image-based CAPTCHAs
            image_captcha_selectors = [
                "img[src*='captcha']",
                "img[alt*='captcha']",
                "img[id*='captcha']",
                "img[class*='captcha']",
                "div[id*='captcha'] img"
            ]
            
            for selector in image_captcha_selectors:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    return True
                    
            # 3. Check for CAPTCHA inputs and labels
            captcha_input_selectors = [
                "input[name*='captcha']",
                "input[id*='captcha']", 
                "#captcha",
                ".captcha input"
            ]
            
            for selector in captcha_input_selectors:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    return True
                    
            # 4. Check for CAPTCHA text in labels, spans, paragraphs
            captcha_phrases = [
                "type the characters",
                "characters you see in the image", 
                "enter the text",
                "security code",
                "verification code",
                "anti-spam",
                "i am not a robot",
                "prove you are human",  # Fixed: removed apostrophe
                "human verification"
            ]
            
            for phrase in captcha_phrases:
                # Using double quotes for the XPath expression to avoid issues with apostrophes
                xpath_selectors = [
                    f'//label[contains(translate(text(), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "{phrase}")]',
                    f'//p[contains(translate(text(), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "{phrase}")]',
                    f'//span[contains(translate(text(), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "{phrase}")]',
                    f'//div[contains(translate(text(), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "{phrase}")]'
                ]
                
                for xpath in xpath_selectors:
                    try:
                        if self.driver.find_elements(By.XPATH, xpath):
                            return True
                    except Exception as e:
                        # Skip invalid XPath expressions
                        logger.debug(f"XPath error in CAPTCHA detection: {str(e)}")
                        continue
                    
            # 5. Check for CAPTCHA-related scripts
            captcha_scripts = [
                "script[src*='recaptcha']",
                "script[src*='hcaptcha']",
                "script[src*='captcha']",
                "script[src*='turnstile']"
            ]
            
            for selector in captcha_scripts:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    return True
                    
            # 6. Check page source for common CAPTCHA terms
            page_source = self.driver.page_source.lower()
            if any(term in page_source for term in ["recaptcha", "hcaptcha", "captcha challenge", "robot verification"]):
                return True
                    
            return False
            
        except Exception as e:
            logger.warning(f"Error in CAPTCHA detection: {str(e)}")
            # Default to assuming no CAPTCHA if we had an error
            return False
    
    def find_form_and_elements(self):
        """Find the main form and all its visible elements - with error handling"""
        try:
            # Find all forms
            forms = self.driver.find_elements(By.TAG_NAME, "form")
            main_container = None
            
            if not forms:
                # No forms found, use body as container if inputs exist
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                if inputs:
                    try:
                        main_container = self.driver.find_element(By.TAG_NAME, "body")
                    except NoSuchElementException:
                        logger.warning("Could not find body element")
                        return None, []
                else:
                    return None, []
            else:
                # Try to find the most promising form
                candidate_forms = []
                
                for form in forms:
                    try:
                        # Count visible input elements
                        visible_inputs = len([e for e in form.find_elements(By.CSS_SELECTOR, 
                                             "input:not([type='hidden']), select, textarea") 
                                             if self.is_element_visible(e)])
                        
                        # Look for common form indicators
                        form_score = visible_inputs * 10  # Base score on number of fields
                        
                        # Boost forms with common input field names
                        common_fields = ["email", "name", "first", "last", "phone", "address"]
                        for field in common_fields:
                            try:
                                if form.find_elements(By.CSS_SELECTOR, f"input[name*='{field}' i], input[id*='{field}' i]"):
                                    form_score += 20
                            except:
                                pass
                        
                        # Boost forms with submit buttons
                        try:
                            if form.find_elements(By.CSS_SELECTOR, "input[type='submit'], button[type='submit']"):
                                form_score += 30
                        except:
                            pass
                            
                        # Add form with its score to candidates
                        candidate_forms.append((form, form_score, visible_inputs))
                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        logger.debug(f"Error scoring form: {str(e)}")
                        continue
                
                # Sort by score (descending)
                candidate_forms.sort(key=lambda x: x[1], reverse=True)
                
                # Select the best form
                if candidate_forms:
                    # Take the highest scoring form with at least 2 visible inputs
                    for form, score, input_count in candidate_forms:
                        if input_count >= 2:
                            main_container = form
                            break
                    # Fallback to highest scoring form if none have enough inputs
                    if not main_container and candidate_forms:
                        main_container = candidate_forms[0][0]
                else:
                    # Fallback to first form if scoring failed
                    try:
                        main_container = forms[0]
                    except (IndexError, StaleElementReferenceException):
                        logger.warning("Could not access forms list")
                        return None, []
            
            # Collect all visible elements from the container
            all_form_elements = []
            selectors = [
                "input:not([type='hidden'])", 
                "select", 
                "textarea", 
                "button",
                "div[role='button']",
                "span[role='button']"
            ]
            
            try:
                for selector in selectors:
                    try:
                        elements = main_container.find_elements(By.CSS_SELECTOR, selector)
                        for element in elements:
                            if self.is_element_visible(element):
                                all_form_elements.append(element)
                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        logger.debug(f"Error finding elements with selector {selector}: {str(e)}")
            except Exception as e:
                logger.warning(f"Error collecting form elements: {str(e)}")
            
            # If few elements found in the main form, search nearby forms or the entire page
            if len(all_form_elements) < 3:
                # First try: look in all other forms 
                for form in forms:
                    if form != main_container:
                        try:
                            for selector in selectors:
                                try:
                                    elements = form.find_elements(By.CSS_SELECTOR, selector)
                                    for element in elements:
                                        if self.is_element_visible(element):
                                            all_form_elements.append(element)
                                except:
                                    continue
                        except:
                            continue
                
                # Second try: if still not enough elements, look in the entire page
                if len(all_form_elements) < 3:
                    all_elements = []
                    for selector in selectors:
                        try:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for element in elements:
                                if self.is_element_visible(element) and element not in all_form_elements:
                                    all_elements.append(element)
                        except:
                            continue
                    all_form_elements.extend(all_elements)
                
            return main_container, all_form_elements
            
        except Exception as e:
            logger.error(f"Error finding form and elements: {str(e)}")
            return None, []
    
    def get_xpath(self, element):
        """Generate optimized XPath for an element with error handling"""
        try:
            # First try to create an optimal XPath using ID if available
            element_id = element.get_attribute('id')
            if element_id and element_id.strip():
                return f"//*[@id='{element_id}']"
                
            # Next try name for inputs
            if element.tag_name in ['input', 'select', 'textarea']:
                name = element.get_attribute('name')
                if name and name.strip():
                    return f"//{element.tag_name}[@name='{name}']"
                    
            # Use JavaScript as fallback
            try:
                return self.driver.execute_script("""
                    function getXPath(element) {
                        if (element.id) return `//*[@id="${element.id}"]`;
                        if (element.name && (element.tagName === 'INPUT' || element.tagName === 'SELECT' || element.tagName === 'TEXTAREA')) 
                            return `//${element.tagName.toLowerCase()}[@name="${element.name}"]`;
                        
                        let path = [];
                        while (element && element.nodeType === 1) {
                            let index = 1;
                            for (let sibling = element.previousSibling; sibling; sibling = sibling.previousSibling) {
                                if (sibling.nodeType === 1 && sibling.tagName === element.tagName) index++;
                            }
                            path.unshift(`${element.tagName.toLowerCase()}[${index}]`);
                            element = element.parentNode;
                        }
                        return `/${path.join('/')}`;
                    }
                    return getXPath(arguments[0]);
                """, element)
            except JavascriptException as js_e:
                logger.debug(f"JavaScript error in XPath generation: {str(js_e)}")
                # Fallback - simple XPath
                tag = element.tag_name
                try:
                    # Try to use class if available
                    element_class = element.get_attribute('class')
                    if element_class and ' ' not in element_class:
                        return f"//{tag}[@class='{element_class}']"
                except:
                    pass
        except Exception as e:
            logger.debug(f"Error in XPath generation: {str(e)}")
            
        # Last resort - very simple path based on tag
        try:
            tag = element.tag_name
            return f"//{tag}"
        except:
            return "//unknown"
    
    def is_element_visible(self, element):
        """Check if an element is visible and usable - with error handling"""
        try:
            return (element.is_displayed() and 
                    element.size['width'] > 0 and 
                    element.size['height'] > 0 and
                    element.value_of_css_property('visibility') != 'hidden')
        except Exception:
            return False
    
    def is_element_required(self, element):
        """Check if a form element is required - with error handling"""
        try:
            return (element.get_attribute("required") == "true" or 
                   element.get_attribute("aria-required") == "true" or
                   "required" in (element.get_attribute("class") or ""))
        except Exception:
            return False
    
    def process_button(self, element, result):
        """Process a button element and update result if it's a submit button - with error handling"""
        try:
            button_text = element.text.strip().lower()
            button_value = (element.get_attribute("value") or "").lower()
            
            if any(term in button_text or term in button_value for term in ["submit", "send", "register", "sign up"]):
                if not result['fields']['Submit']['found']:
                    result['fields']['Submit'] = {
                        'xpath': self.get_xpath(element),
                        'type': element.get_attribute("type") or "button",
                        'required': True,
                        'found': True
                    }
        except Exception:
            pass
    
    def find_submit_buttons(self):
        """Find submit buttons using various methods - with error handling"""
        # Try these selectors in order
        selectors = [
            "input[type='submit']",
            "button[type='submit']",
            ".submit-button",
            "button.submit",
            "input.submit",
            ".btn-primary", 
            "button"
        ]
        
        for selector in selectors:
            try:
                buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                visible_buttons = []
                for button in buttons:
                    try:
                        if self.is_element_visible(button):
                            visible_buttons.append(button)
                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        logger.debug(f"Error checking button visibility: {str(e)}")
                
                # First check for buttons with submit-like text
                for button in visible_buttons:
                    try:
                        text = (button.text or "").lower()
                        value = (button.get_attribute("value") or "").lower()
                        
                        if any(term in text or term in value for term in ["submit", "send", "register", "sign up"]):
                            return [button]
                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        logger.debug(f"Error checking button text: {str(e)}")
                
                # If no text match, return any visible buttons of this type
                if visible_buttons:
                    return visible_buttons
            except Exception as e:
                logger.debug(f"Error finding buttons with selector {selector}: {str(e)}")
        
        # No buttons found
        return []
    
    def find_privacy_checkbox(self, elements):
        """Find a privacy/terms checkbox in the form - with error handling"""
        privacy_terms = ["privacy", "terms", "policy", "agree", "consent", "gdpr"]
        
        for element in elements:
            try:
                element_type = element.get_attribute("type")
                if element_type in ['checkbox', 'radio']:
                    # Check element attributes
                    for attr in ['name', 'id', 'aria-label']:
                        try:
                            value = (element.get_attribute(attr) or "").lower()
                            if any(term in value for term in privacy_terms):
                                return element
                        except:
                            continue
                    
                    # Check nearby text (parent and labels)
                    try:
                        # Parent text
                        parent = element.find_element(By.XPATH, "./..")
                        if any(term in parent.text.lower() for term in privacy_terms):
                            return element
                            
                        # Associated label
                        element_id = element.get_attribute('id')
                        if element_id:
                            labels = self.driver.find_elements(By.CSS_SELECTOR, f"label[for='{element_id}']")
                            for label in labels:
                                if any(term in label.text.lower() for term in privacy_terms):
                                    return element
                    except:
                        pass
            except StaleElementReferenceException:
                continue
            except Exception as e:
                logger.debug(f"Error checking for privacy checkbox: {str(e)}")
        
        return None
    
    def find_best_candidate_for_field(self, elements, field_name, field_detector):
        """Find the best candidate for a specific field from a list of elements - with error handling"""
        candidates = []
        patterns = field_detector.field_patterns.get(field_name, [])
        
        for element in elements:
            try:
                element_type = element.get_attribute("type") or element.tag_name
                if element_type == 'hidden':
                    continue
                
                # Score based on element type
                score = 0
                if ((field_name == "Email" and element_type == "email") or
                    (field_name == "Phone" and element_type == "tel")):
                    score += 50
                
                # Score based on attributes
                attrs = {}
                for attr in ['name', 'id', 'placeholder', 'aria-label']:
                    try:
                        attrs[attr] = (element.get_attribute(attr) or "").lower()
                    except:
                        attrs[attr] = ""
                
                # Check for direct matches in attributes
                for attr, value in attrs.items():
                    if value:
                        # Direct pattern matches
                        for pattern in patterns:
                            if pattern in value:
                                score += 30
                            if re.search(r'\b' + re.escape(pattern) + r'\b', value):
                                score += 50
                        
                        # Special case for name fields
                        if field_name in ["FirstName", "LastName"]:
                            try:
                                name_match = re.search(r'(?:^|_|-)(?:first|last)(?:_|-|$|name)', value)
                                if name_match:
                                    field_part = name_match.group(0)
                                    if (field_name == "FirstName" and "first" in field_part) or \
                                       (field_name == "LastName" and "last" in field_part):
                                        score += 100
                            except:
                                pass
                    
                # If score is positive, add to candidates
                if score > 0:
                    candidates.append((element, score))
            except StaleElementReferenceException:
                continue
            except Exception as e:
                logger.debug(f"Error evaluating field candidate: {str(e)}")
                continue
            
        # If there are multiple text fields with 'name' in the attribute but no specific first/last
        # Try to make an educated guess based on field order
        if field_name in ["FirstName", "LastName"] and not candidates:
            name_fields = []
            for element in elements:
                try:
                    element_type = element.get_attribute("type")
                    if element_type == 'text':
                        for attr in ['name', 'id', 'placeholder']:
                            try:
                                value = (element.get_attribute(attr) or "").lower()
                                if 'name' in value and 'first' not in value and 'last' not in value:
                                    name_fields.append(element)
                                    break
                            except:
                                continue
                except:
                    continue
            
            # If we have exactly two name fields, assume first=FirstName, second=LastName
            if len(name_fields) == 2:
                if field_name == "FirstName":
                    candidates.append((name_fields[0], 10))
                else:  # LastName
                    candidates.append((name_fields[1], 10))
        
        # Sort candidates by score and return the best one
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0] if candidates else None