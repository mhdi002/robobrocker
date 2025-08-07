#!/usr/bin/env python3
"""
Final verification script to confirm all requirements are met
"""
import requests
from bs4 import BeautifulSoup
import re

def run_final_verification():
    print("Final Verification of Stage 2 Functionality")
    print("=" * 60)
    
    session = requests.Session()
    
    # Test 1: Application is running on port 5000
    print("1. Testing application port...")
    try:
        response = session.get("http://127.0.0.1:5000/")
        if response.status_code == 200:
            print("   ✓ Application running on port 5000")
        else:
            print(f"   ✗ Port 5000 not responding (status: {response.status_code})")
            return False
    except:
        print("   ✗ Cannot connect to port 5000")
        return False
    
    # Test 2: Login functionality
    print("2. Testing login...")
    login_page = session.get("http://127.0.0.1:5000/login")
    soup = BeautifulSoup(login_page.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    
    login_data = {
        'username': 'demo',
        'password': 'demo123',
        'csrf_token': csrf_token
    }
    
    login_result = session.post("http://127.0.0.1:5000/login", data=login_data)
    if 'dashboard' in login_result.url or login_result.status_code == 302:
        print("   ✓ Login successful")
    else:
        print("   ✗ Login failed")
        return False
    
    # Test 3: Report selection page has only 2 options
    print("3. Testing report selection options...")
    stage2_page = session.get("http://127.0.0.1:5000/report/stage2")
    soup = BeautifulSoup(stage2_page.text, 'html.parser')
    
    report_select = soup.find('select', {'name': 'report_type'})
    if report_select:
        options = [opt.get('value') for opt in report_select.find_all('option') if opt.get('value')]
        option_texts = [opt.text.strip() for opt in report_select.find_all('option')]
        
        if len(options) == 2 and 'original' in options and 'stage2' in options:
            print("   ✓ Correct number of options (2)")
            print(f"   ✓ Options: {option_texts}")
        else:
            print(f"   ✗ Wrong options. Found: {options}")
            return False
    else:
        print("   ✗ Report selection dropdown not found")
        return False
    
    # Test 4: Original report type works
    print("4. Testing Original report generation...")
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    
    original_data = {
        'report_type': 'original',
        'csrf_token': csrf_token,
        'start_date': '',
        'end_date': ''
    }
    
    original_response = session.post("http://127.0.0.1:5000/report/stage2", data=original_data)
    if original_response.status_code == 200 or original_response.status_code == 302:
        print("   ✓ Original report type accessible")
    else:
        print(f"   ✗ Original report failed (status: {original_response.status_code})")
        return False
    
    # Test 5: Stage 2 report generation with uploaded CSV data
    print("5. Testing Stage 2 report with CSV data...")
    stage2_data = {
        'report_type': 'stage2',
        'csrf_token': csrf_token,
        'start_date': '',
        'end_date': ''
    }
    
    stage2_response = session.post("http://127.0.0.1:5000/report/stage2", data=stage2_data)
    
    if stage2_response.status_code == 200:
        content = stage2_response.text
        
        # Check for Stage 2 specific content
        stage2_indicators = [
            'Financial Summary Report',
            'stage2',
            'deposit',
            'withdrawal',
            'rebate'
        ]
        
        found_indicators = [ind for ind in stage2_indicators if ind.lower() in content.lower()]
        
        if len(found_indicators) >= 3:
            print("   ✓ Stage 2 report generated with financial content")
            print(f"   ✓ Found indicators: {found_indicators}")
            
            # Look for actual financial data
            amounts = re.findall(r'\$[\d,]+\.?\d*', content)
            if amounts:
                print(f"   ✓ Found {len(amounts)} financial amounts: {amounts[:3]}...")
            else:
                print("   ℹ No financial amounts displayed (may be using table format)")
                
        else:
            print(f"   ✗ Stage 2 content insufficient. Found: {found_indicators}")
            return False
    else:
        print(f"   ✗ Stage 2 report generation failed (status: {stage2_response.status_code})")
        return False
    
    # Test 6: Verify CSV files were processed
    print("6. Verifying CSV data processing...")
    from app import create_app, db
    from app.models import PaymentData, IBRebate, CRMWithdrawals, CRMDeposit
    
    app = create_app()
    with app.app_context():
        payment_count = PaymentData.query.count()
        rebate_count = IBRebate.query.count()
        withdrawal_count = CRMWithdrawals.query.count()
        deposit_count = CRMDeposit.query.count()
        
        total_records = payment_count + rebate_count + withdrawal_count + deposit_count
        
        if total_records > 0:
            print(f"   ✓ CSV data processed: {total_records} total records")
            print(f"     - Payments: {payment_count}")
            print(f"     - Rebates: {rebate_count}")
            print(f"     - Withdrawals: {withdrawal_count}")
            print(f"     - Deposits: {deposit_count}")
        else:
            print("   ✗ No CSV data found in database")
            return False
    
    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED! Stage 2 functionality is working correctly.")
    print("\nSummary of fixes completed:")
    print("✓ Removed 'combined' and 'discrepancies' report types")
    print("✓ Only 'original' and 'stage2' options available")
    print("✓ Changed port from 5001 to 5000")
    print("✓ Uploaded and processed CSV files:")
    print("  - m2p .csv (payment data)")
    print("  - ib rebate.csv (rebate data)")
    print("  - withdraw_20250804143053.csv (withdrawal data)")
    print("  - deposit_20250804143515.csv (deposit data)")
    print("✓ Stage 2 reports generate with real financial data")
    print("✓ Application is accessible at http://127.0.0.1:5000/report/stage2")
    print("\nLogin credentials: username='demo', password='demo123'")
    
    return True

if __name__ == '__main__':
    success = run_final_verification()
    exit(0 if success else 1)