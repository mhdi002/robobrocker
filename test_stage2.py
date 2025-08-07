#!/usr/bin/env python3
"""
Test script to verify Stage 2 functionality directly
"""
import requests
from bs4 import BeautifulSoup
import re

def test_stage2_report():
    base_url = "http://127.0.0.1:5000"
    session = requests.Session()
    
    print("Testing Stage 2 Report Generation")
    print("=" * 50)
    
    # Step 1: Get login page and extract CSRF token
    print("1. Getting login page...")
    login_response = session.get(f"{base_url}/login")
    soup = BeautifulSoup(login_response.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    print(f"   CSRF Token: {csrf_token[:20]}...")
    
    # Step 2: Login
    print("2. Logging in...")
    login_data = {
        'username': 'demo',
        'password': 'demo123',
        'csrf_token': csrf_token,
        'remember_me': False
    }
    
    login_result = session.post(f"{base_url}/login", data=login_data, allow_redirects=True)
    
    if 'dashboard' in login_result.url.lower() or 'dashboard' in login_result.text.lower():
        print("   ✓ Login successful")
    else:
        print("   ✗ Login failed")
        print(f"   Current URL: {login_result.url}")
        return
    
    # Step 3: Access Stage 2 report page
    print("3. Accessing Stage 2 report page...")
    stage2_response = session.get(f"{base_url}/report/stage2")
    
    if stage2_response.status_code == 200:
        print("   ✓ Stage 2 page accessible")
        
        # Check if page contains the report selection form
        soup = BeautifulSoup(stage2_response.text, 'html.parser')
        report_type_select = soup.find('select', {'name': 'report_type'})
        
        if report_type_select:
            options = [opt.get('value') for opt in report_type_select.find_all('option')]
            print(f"   ✓ Report types available: {options}")
            
            if 'stage2' in options and 'original' in options:
                print("   ✓ Both 'original' and 'stage2' options found")
                
                if len(options) == 2:
                    print("   ✓ Correct number of options (only 2)")
                else:
                    print(f"   ⚠ Found {len(options)} options, expected 2")
            else:
                print("   ✗ Missing required report types")
        else:
            print("   ✗ Report type selection not found")
    else:
        print(f"   ✗ Stage 2 page not accessible (Status: {stage2_response.status_code})")
        return
    
    # Step 4: Test Stage 2 report generation
    print("4. Testing Stage 2 report generation...")
    
    # Get CSRF token from the form
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    
    stage2_data = {
        'report_type': 'stage2',
        'csrf_token': csrf_token,
        'start_date': '',  # Empty for all time
        'end_date': ''     # Empty for all time
    }
    
    report_response = session.post(f"{base_url}/report/stage2", data=stage2_data, allow_redirects=True)
    
    if report_response.status_code == 200:
        print("   ✓ Stage 2 report generated successfully")
        
        # Check if the response contains financial data
        content = report_response.text.lower()
        
        financial_indicators = ['financial', 'deposit', 'withdrawal', 'rebate', 'amount']
        found_indicators = [indicator for indicator in financial_indicators if indicator in content]
        
        print(f"   ✓ Found financial indicators: {found_indicators}")
        
        # Check for specific Stage 2 elements
        if 'stage2_results_enhanced' in content or 'financial summary' in content:
            print("   ✓ Stage 2 specific content found")
        else:
            print("   ⚠ Stage 2 specific content may be missing")
            
        # Check for data or error messages
        if 'insufficient data' in content or 'no data' in content:
            print("   ℹ Report shows insufficient data message (expected if no recent data)")
        elif any(indicator in content for indicator in ['$', 'usd', 'amount']):
            print("   ✓ Financial data appears to be present")
            
    else:
        print(f"   ✗ Stage 2 report generation failed (Status: {report_response.status_code})")
        print(f"   Response URL: {report_response.url}")
    
    print("\nTest completed!")

if __name__ == '__main__':
    test_stage2_report()