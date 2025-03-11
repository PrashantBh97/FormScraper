import csv
import json
import re
import os
from urllib.parse import urlparse


def parse_additional_fields(row):
    """Parse additional fields from the CSV row into a structured list, including only required fields"""
    additional_fields = []
    i = 1
    
    while True:
        name_key = f"AdditionalField{i}Name"
        type_key = f"AdditionalField{i}Type"
        xpath_key = f"AdditionalField{i}XPath"
        required_key = f"AdditionalField{i}Required"
        
        # Check if we've reached the end of additional fields
        if name_key not in row or not row[name_key]:
            break
            
        # Convert string 'True'/'False' to boolean
        required = False
        if required_key in row:
            required = row[required_key] == "True"
        
        # Only include required additional fields
        if required:
            additional_fields.append({
                "name": row[name_key],
                "type": row[type_key] if type_key in row and row[type_key] else "",
                "xpath": row[xpath_key] if xpath_key in row and row[xpath_key] else "",
                "required": True  # Always true since we're filtering for required fields
            })
        
        i += 1
        
    return additional_fields


def convert_csv_to_json(csv_file, json_file):
    """Convert form fields CSV to a structured JSON format for automation"""
    data = []
    standard_fields = [
        "Title", "FirstName", "LastName", "Email", "ConfirmEmail", 
        "JobTitle", "Organization", "Phone", "Street", "City",
        "State", "Zipcode", "Country", "Privacy", "Submit"
    ]
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for index, row in enumerate(reader, 1):
            url = row['url']
            domain = row['domain'] or urlparse(url).netloc
            
            form_data = {
                "url_id": index,  # New unique identifier for each URL
                "url": url,
                "domain": domain,
                "has_captcha": row.get("HasCaptcha", "").lower() == "true",
                "error": row.get("error", ""),
                "fields": {},
                "additional_fields": parse_additional_fields(row)
            }
            
            # Parse standard fields
            for field in standard_fields:
                type_key = f"{field}Type"
                xpath_key = f"{field}XPath"
                
                # Only include fields that were found
                if xpath_key in row and row[xpath_key]:
                    form_data["fields"][field] = {
                        "type": row[type_key] if type_key in row else "",
                        "xpath": row[xpath_key],
                        # Usually all fields are required except Privacy sometimes
                        "required": field != "Privacy" if field != "ConfirmEmail" else False
                    }
            
            data.append(form_data)
    
    # Create directories if needed
    os.makedirs(os.path.dirname(json_file) if os.path.dirname(json_file) else '.', exist_ok=True)
    
    # Write the JSON with proper formatting
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    return data


def main():
    # Hardcoded file paths
    csv_file = "form_fields_new.csv"
    json_file = "form_fields.json"
    
    print(f"Converting {csv_file} to {json_file}...")
    data = convert_csv_to_json(csv_file, json_file)
    print(f"Conversion complete. Processed {len(data)} form entries.")
    print(f"JSON output saved to: {json_file}")


if __name__ == "__main__":
    main()