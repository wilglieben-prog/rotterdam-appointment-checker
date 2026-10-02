from selenium import webdriver 
from selenium.webdriver.common.by import By 
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup 
import time 
import requests 
import urllib.parse 
import datetime
import os
import atexit
import re
from dateutil import parser

# Global WebDriver instance (singleton pattern to reuse browser)
_driver_instance = None

def get_driver():
    """Get or create a singleton WebDriver instance"""
    global _driver_instance
    
    if _driver_instance is None:
        print("Creating new Chrome WebDriver instance...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        # Add memory optimization flags
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-default-apps")
        
        _driver_instance = webdriver.Chrome(options=chrome_options)
        print("Chrome WebDriver instance created successfully")
        
        # Register cleanup on exit
        atexit.register(cleanup_driver)
    
    return _driver_instance

def is_date_after_cutoff(date_string, cutoff_date):
    """
    Check if a date is after the specified cutoff date.
    Tries to parse various date formats from the date_string.
    Returns True if the date is after cutoff, False otherwise or if parsing fails.
    """
    try:
        # Try to parse the date using dateutil parser which handles many formats
        parsed_date = parser.parse(date_string, dayfirst=True, fuzzy=True)
        
        print(f"Parsed date: {parsed_date.strftime('%Y-%m-%d')}, Cutoff: {cutoff_date.strftime('%Y-%m-%d')}")
        return parsed_date > cutoff_date
    except Exception as e:
        print(f"Could not parse date from '{date_string}': {e}")
        # If we can't parse the date, err on the side of notifying
        return True

def get_date_filter():
    """
    Get the minimum date filter from environment variable.
    Returns a datetime object if MIN_DATE_FILTER is set, None otherwise.
    
    MIN_DATE_FILTER format examples:
    - "2024-12-21" (ISO format)
    - "21-12-2024" or "21/12/2024" (day first)
    - "December 21, 2024"
    """
    min_date_str = os.environ.get('MIN_DATE_FILTER', '').strip()
    
    if not min_date_str:
        print("No MIN_DATE_FILTER set - will notify for all available appointments")
        return None
    
    try:
        # Parse the date from environment variable
        cutoff_date = parser.parse(min_date_str, dayfirst=True)
        print(f"Date filter enabled: Only notifying for appointments after {cutoff_date.strftime('%Y-%m-%d')}")
        return cutoff_date
    except Exception as e:
        print(f"Warning: Could not parse MIN_DATE_FILTER '{min_date_str}': {e}")
        print("Will notify for all available appointments")
        return None

def cleanup_driver():
    """Clean up the WebDriver instance"""
    global _driver_instance
    if _driver_instance is not None:
        try:
            print("Cleaning up Chrome WebDriver...")
            _driver_instance.quit()
            _driver_instance = None
            print("Chrome WebDriver cleaned up successfully")
        except Exception as e:
            print(f"Error cleaning up driver: {e}")

def reset_driver():
    """Reset the driver if it's in a bad state"""
    global _driver_instance
    if _driver_instance is not None:
        cleanup_driver()
    return get_driver()

# Function to send a push notification via ntfy.sh with priority
def send_notification_with_priority(message, title, priority="default"):
    # Get the ntfy topic from environment variable (or use default)
    ntfy_topic = os.environ.get('NTFY_TOPIC', 'rotterdam-appointments-default')
    ntfy_url = f'https://ntfy.sh/{ntfy_topic}'
    
    # Set tags based on priority
    if priority == "urgent":
        tags = "tada,rotating_light,calendar"
        priority_val = "urgent"
    else:
        tags = "clipboard,calendar"
        priority_val = "default"
    
    try:
        # Use query parameters for better emoji support
        params = {
            'title': title,
            'priority': priority_val,
            'tags': tags
        }
        
        response = requests.post(
            ntfy_url,
            data=message.encode('utf-8'),
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"Notification sent successfully to ntfy topic: {ntfy_topic}")
        else:
            print(f"Failed to send notification. Status code: {response.status_code}, response: {response.text}")
    except Exception as e:
        print(f"Error sending notification: {e}")


def main():
    """Main function to check appointments"""
    # Get the date filter (if any)
    date_cutoff = get_date_filter()
    
    # Get the reusable driver instance
    try:
        driver = get_driver()
    except Exception as e:
        print(f"Failed to get driver, attempting reset: {e}")
        driver = reset_driver()
    
    # Open the URL
    driver.get("https://concern.ir.rotterdam.nl/afspraak/maken/product/indienen-naturalisatieverzoek") 

    try:
        # Get the current date and time
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Script started at: {current_time}")

        time.sleep(3)  # Wait for page to fully load
        
        # Try to find and interact with the form elements
        # The form structure may have changed, so we'll try multiple approaches
        
        # First, check if we need to select number of people
        try:
            print("Looking for number of people dropdown...")
            # Try to find any select dropdown on the page
            dropdowns = driver.find_elements(By.TAG_NAME, "select")
            
            number_dropdown = None
            for dropdown in dropdowns:
                try:
                    dropdown_name = dropdown.get_attribute('name') or ''
                    dropdown_id = dropdown.get_attribute('id') or ''
                    if dropdown_name in ('taal', 'sortering') or dropdown_id in ('id2', 'ida'):
                        continue
                    dropdown_html = dropdown.get_attribute('outerHTML')
                    if 'aantal' in dropdown_html.lower() or len(dropdown.find_elements(By.TAG_NAME, "option")) <= 5:
                        number_dropdown = dropdown
                        print(f"Found potential number dropdown: {dropdown_id}")
                        break
                except:
                    continue
            
            if number_dropdown:
                number_dropdown_id = number_dropdown.get_attribute('id')
                select = Select(number_dropdown)
                # Try to select by visible text first (more reliable)
                options = select.options
                print(f"Available options: {[opt.text for opt in options]}")
                
                # Select 1 person (by visible text "1")
                print("People setting in this version: 1 person")
                select.select_by_visible_text("1")
                time.sleep(2)  # page may refresh the form after changing the dropdown
                # Re-read the dropdown from the page to confirm what is really selected
                confirmed = Select(driver.find_element(By.ID, number_dropdown_id)).first_selected_option.text
                print(f"Selected option: {confirmed}")
                if confirmed.strip() != "1":
                    print("Dropdown did not stick at 1, selecting again...")
                    Select(driver.find_element(By.ID, number_dropdown_id)).select_by_visible_text("1")
                    time.sleep(2)
                    confirmed = Select(driver.find_element(By.ID, number_dropdown_id)).first_selected_option.text
                    print(f"Selected option after retry: {confirmed}")
                
                time.sleep(1)
            else:
                print("No number of people dropdown found - form may have changed or not needed")
        except Exception as e:
            print(f"Could not find/interact with number dropdown: {e}")
            print("Continuing anyway - form may have changed")
        
        # Try to find and click the "Verder" (Continue) button
        try:
            print("Looking for submit/continue button...")
            time.sleep(1)
            
            # Try multiple ways to find the button
            verder_button = None
            
            # Method 1: Try by text content
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                if "verder" in button.text.lower() or "continue" in button.text.lower():
                    verder_button = button
                    print(f"Found button by text: {button.text}")
                    break
            
            # Method 2: Try by type="submit"
            if not verder_button:
                submit_buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                if submit_buttons:
                    verder_button = submit_buttons[0]
                    print("Found submit button")
            
            if verder_button:
                # Use JavaScript click to avoid interception issues
                driver.execute_script("arguments[0].click();", verder_button)
                print("Clicked continue button")
                time.sleep(3)
            else:
                print("No continue button found - may already be on results page")
        except Exception as e:
            print(f"Could not find/click continue button: {e}")
            print("May already be on results page or form changed")
        
        # Wait for results page to load completely
        print("Waiting for results to load...")
        time.sleep(2)

        # Parse the updated HTML content with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Look for all buttons with class 'list-group-item-action' and not disabled
        available_dates = soup.find_all('button', class_='list-group-item-action')

        # Check for alert warning (no dates available)
        alert_no_dates = soup.find_all('div', class_='alert-warning')

        if alert_no_dates:
            message_first_part = "No available dates alert found."
            print(message_first_part)
        else:
            message_first_part = "Found something."
            print(message_first_part)

        # Filter out "Wachtrij beschikbaar" (waiting list) entries and optionally filter by date
        actual_available_slots = []
        
        if available_dates:
            for date_button in available_dates:
                if date_button.get('disabled') is None:
                    location = date_button.find('h3').text.strip() if date_button.find('h3') else ""
                    date_time_elem = date_button.find('p')
                    date_time = date_time_elem.text.strip() if date_time_elem else ""
                    
                    # Clean up the date/time text (remove "from" prefix if present)
                    date_time = date_time.replace('from ', '').replace('vanaf ', '').strip()
                    
                    print(f"Found slot: {location} - {date_time}")
                    
                    # Skip if it's a waiting list entry
                    if "Wachtrij beschikbaar" in date_time or "wachtrij" in date_time.lower():
                        print(f"  -> Skipping: waiting list entry")
                        continue
                    
                    # Skip if no actual date/time found
                    if not date_time or len(date_time) < 5:
                        print(f"  -> Skipping: no valid date/time")
                        continue
                    
                    # Check if the date is after cutoff (only if cutoff is set)
                    if date_cutoff is not None:
                        if not is_date_after_cutoff(date_time, date_cutoff):
                            print(f"  -> Skipping: before cutoff date")
                            continue
                    
                    # This is an actual available slot (and after cutoff if filter is set)!
                    print(f"  -> Adding to available slots!")
                    actual_available_slots.append(f"{location}: {date_time}")

        if actual_available_slots:
            # We found actual appointment slots!
            date_info = "\n".join(actual_available_slots)
            
            # Create message with optional date filter info
            if date_cutoff:
                filter_msg = f" (After {date_cutoff.strftime('%B %d, %Y')})"
                title_filter = f" (After {date_cutoff.strftime('%b %d')})"
            else:
                filter_msg = ""
                title_filter = ""
            
            message = f"🎉🎉🎉 APPOINTMENT SLOTS AVAILABLE{filter_msg}! 🎉🎉🎉\n\n{date_info}\n\nCheck immediately:\nhttps://concern.ir.rotterdam.nl/afspraak/maken/product/indienen-naturalisatieverzoek\n\nMessage Sent at: {current_time}"
            print(message)
            
            # Send the notification with high priority and special title
            send_notification_with_priority(message, f"🎉 SLOTS AVAILABLE{title_filter}!", "urgent")
        else:
            if date_cutoff:
                print(f"No appointment slots found after {date_cutoff.strftime('%Y-%m-%d')}.")
            else:
                print("No actual appointment slots found (only waiting list or nothing).")
            print(f"Check completed at: {current_time} - No notification sent")

    except Exception as e:
        error_message = f"❌ ERROR: Script failed with exception: {str(e)}\nTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        print(error_message)
        send_notification_with_priority(error_message, "❌ Script Error", "high")
        
        # Reset driver on error
        print("Resetting driver due to error...")
        reset_driver()
    
    finally:
        # Don't close the driver - reuse it for next run
        # Just navigate away to clear state
        try:
            driver.get("about:blank")
        except:
            pass
        print("Check completed, driver ready for next run")

if __name__ == "__main__":
    main()
