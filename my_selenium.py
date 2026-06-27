# my_selenium.py



# driver = webdriver.Chrome(service=service)
# driver.get("http://localhost:8501")



import json
import os
import time
from pathlib import Path
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BROWSER = "chrome"   # "chrome" or "edge"
# BROWSER = "edge"   # "chrome" or "edge"
URL = "http://localhost:8501"
OUTPUT_DIR = Path(r"C:\temp\pdf_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def make_driver(browser_name):
    print_settings = {
        "recentDestinations": [
            {"id": "Save as PDF", "origin": "local", "account": ""}
        ],
        "selectedDestinationId": "Save as PDF",
        "version": 2,
        "isHeaderFooterEnabled": False,
        "isLandscapeEnabled": False
    }

    prefs = {
        "download.prompt_for_download": False,
        "download.default_directory": str(OUTPUT_DIR),
        "savefile.default_directory": str(OUTPUT_DIR),
        "printing.print_preview_sticky_settings.appState": json.dumps(print_settings)
    }

    if browser_name.lower() == "chrome":
        from selenium.webdriver.chrome.service import Service
        options = webdriver.ChromeOptions()
        options.add_experimental_option("prefs", prefs)
        options.add_argument("--kiosk-printing")
        service = Service("/Users/shaibaranes/tools/chromedriver/chromedriver")
        return webdriver.Chrome(service=service, options=options)

    elif browser_name.lower() == "edge":
        from selenium.webdriver.edge.service import Service
        options = webdriver.EdgeOptions()
        options.add_experimental_option("prefs", prefs)
        options.add_argument("--kiosk-printing")
        service = Service(r"C:\tools\msedgedriver.exe")
        return webdriver.Edge(service=service, options=options)

    else:
        raise ValueError("Unsupported browser")

def wait_for_streamlit_idle():
    time.sleep(3)

def switch_streamlit_page(driver, wait, page_label):
    elem = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//*[normalize-space()='{page_label}']")
        )
    )
    driver.execute_script("arguments[0].click();", elem)
    wait_for_streamlit_idle()

def save_current_page_as_pdf(driver, name):
    driver.execute_script(f"document.title='{name}';")
    time.sleep(1)
    driver.execute_script("window.print();")
    time.sleep(5)

driver = make_driver(BROWSER)
wait = WebDriverWait(driver, 30)

try:
    driver.get(URL)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    wait_for_streamlit_idle()

    # ----- PAGE 1 -----
    # Put your page-1 interactions here
    # Example:
    # upload = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"]')))
    # upload.send_keys(r"C:\data\my_file.csv")
    # run_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[.//p[contains(., 'Run')]]")))
    # run_btn.click()
    # wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(., 'Done')]")))

    save_current_page_as_pdf(driver, "page1_report")

    # ----- SWITCH TO PAGE 2 -----
    switch_streamlit_page(driver, wait, "KPIs")
    # switch_streamlit_page(driver, wait, "1_📊_KPIs")
    # switch_streamlit_page(driver, wait, "My Other Page")

    # ----- PAGE 2 -----
    # Put your page-2 interactions here
    # Example:
    # wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(., 'Second page title')]")))
    # filter_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[.//p[contains(., 'Apply')]]")))
    # filter_btn.click()
    # wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(., 'Updated results')]")))

    save_current_page_as_pdf(driver, "page2_report")

finally:
    driver.quit()