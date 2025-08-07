#!/usr/bin/env python3
"""
Script to automatically upload and process test CSV files for Stage 2 functionality
"""
import os
import shutil
from app import create_app, db
from app.models import User, UploadedFiles, PaymentData, IBRebate, CRMWithdrawals, CRMDeposit
from datetime import datetime
import pandas as pd
import uuid

def process_payment_data_with_user(file_path, user_id, file_format='csv'):
    """Process payment CSV data for a specific user"""
    try:
        if file_format.lower() == 'xlsx':
            data = pd.read_excel(file_path)
        else:
            data = pd.read_csv(file_path)
        
        if data.empty or len(data) < 1:
            raise ValueError("File is empty or invalid")
        
        headers = data.columns.tolist()
        rows = data.values.tolist()
        
        added_count = 0
        
        for row in rows:
            try:
                # Create row dictionary
                row_dict = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        row_dict[header.strip()] = row[i]
                
                # Extract values using flexible column mapping
                tx_id = str(row_dict.get('Transaction ID', '')).strip()
                status = str(row_dict.get('Status', '')).upper()
                pg_name = str(row_dict.get('Payment gateway', '')).upper()
                tx_type = str(row_dict.get('Type', '')).upper()
                
                if not tx_id or pg_name == 'BALANCE' or status != 'DONE':
                    continue
                
                # Check if already exists
                existing = PaymentData.query.filter_by(tx_id=tx_id).first()
                if existing:
                    continue
                
                # Determine sheet category
                sheet_category = ''
                if tx_type == 'DEPOSIT':
                    sheet_category = 'Settlement Deposit' if 'SETTLEMENT' in pg_name else 'M2p Deposit'
                else:
                    sheet_category = 'Settlement Withdraw' if 'SETTLEMENT' in pg_name else 'M2p Withdraw'
                
                # Parse date
                created_date = None
                booked_str = row_dict.get('Booked', '')
                if booked_str:
                    try:
                        created_date = pd.to_datetime(booked_str).to_pydatetime()
                    except:
                        pass
                
                # Create new payment record
                payment = PaymentData(
                    user_id=user_id,
                    confirmed=row_dict.get('Confirmed', ''),
                    tx_id=tx_id,
                    wallet_address=row_dict.get('Wallet address', ''),
                    status=status,
                    type=tx_type,
                    payment_gateway=row_dict.get('Payment gateway', ''),
                    final_amount=float(row_dict.get('Final amount', 0) or 0),
                    final_currency=row_dict.get('Final currency', ''),
                    settlement_amount=float(row_dict.get('Settlement amount', 0) or 0),
                    settlement_currency=row_dict.get('Settlement currency', ''),
                    processing_fee=float(row_dict.get('Processing fee', 0) or 0),
                    price=float(row_dict.get('Price', 1) or 1),
                    comment=row_dict.get('Comment', ''),
                    payment_id=row_dict.get('Payment ID', ''),
                    created=created_date,
                    trading_account=row_dict.get('Trading account', ''),
                    correct_coin_sent=True,
                    balance_after=float(row_dict.get('Balance after', 0) or 0),
                    tier_fee=float(row_dict.get('Tier fee', 0) or 0),
                    sheet_category=sheet_category
                )
                
                db.session.add(payment)
                added_count += 1
                
            except Exception as e:
                print(f"Error processing payment row: {e}")
                continue
        
        db.session.commit()
        return {'added_rows': added_count, 'total_rows': len(rows)}
        
    except Exception as e:
        db.session.rollback()
        raise e

def process_ib_rebate_with_user(file_path, user_id, file_format='csv'):
    """Process IB Rebate CSV data for a specific user"""
    try:
        if file_format.lower() == 'xlsx':
            data = pd.read_excel(file_path)
        else:
            data = pd.read_csv(file_path)
        
        if data.empty:
            raise ValueError("File is empty or invalid")
        
        headers = data.columns.tolist()
        rows = data.values.tolist()
        
        added_count = 0
        
        for row in rows:
            try:
                # Create row dictionary
                row_dict = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        row_dict[header.strip()] = row[i]
                
                tx_id = str(row_dict.get('Transaction ID', '')).strip()
                if not tx_id:
                    continue
                
                # Check if already exists
                existing = IBRebate.query.filter_by(transaction_id=tx_id).first()
                if existing:
                    continue
                
                rebate_value = float(row_dict.get('Rebate', 0) or 0)
                
                # Parse rebate time
                rebate_time = None
                rebate_time_str = row_dict.get('Rebate Time', '')
                if rebate_time_str:
                    try:
                        rebate_time = pd.to_datetime(rebate_time_str).to_pydatetime()
                    except:
                        pass
                
                rebate = IBRebate(
                    user_id=user_id,
                    transaction_id=tx_id,
                    rebate=rebate_value,
                    rebate_time=rebate_time
                )
                
                db.session.add(rebate)
                added_count += 1
                
            except Exception as e:
                print(f"Error processing rebate row: {e}")
                continue
        
        db.session.commit()
        return {'added_rows': added_count, 'total_rows': len(rows)}
        
    except Exception as e:
        db.session.rollback()
        raise e

def process_crm_withdrawals_with_user(file_path, user_id, file_format='csv'):
    """Process CRM Withdrawals CSV data for a specific user"""
    try:
        if file_format.lower() == 'xlsx':
            data = pd.read_excel(file_path)
        else:
            data = pd.read_csv(file_path)
        
        if data.empty:
            raise ValueError("File is empty or invalid")
        
        headers = data.columns.tolist()
        rows = data.values.tolist()
        
        added_count = 0
        
        for row in rows:
            try:
                # Create row dictionary
                row_dict = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        row_dict[header.strip()] = row[i]
                
                request_id = str(row_dict.get('Request ID', '')).strip()
                if not request_id:
                    continue
                
                # Check if already exists
                existing = CRMWithdrawals.query.filter_by(request_id=request_id).first()
                if existing:
                    continue
                
                # Process withdrawal amount (handle USC conversion)
                amount_val = str(row_dict.get('Withdrawal Amount', '')).strip().upper()
                amount = 0
                if amount_val:
                    import re
                    if 'USD' in amount_val:
                        amount = float(re.sub(r'[^0-9.-]', '', amount_val))
                    elif 'USC' in amount_val:
                        raw_amount = float(re.sub(r'[^0-9.-]', '', amount_val))
                        amount = raw_amount / 100 if not pd.isna(raw_amount) else 0
                    else:
                        amount = float(re.sub(r'[^0-9.-]', '', amount_val)) if amount_val else 0
                
                # Parse review time
                review_time = None
                review_time_str = row_dict.get('Review Time', '')
                if review_time_str:
                    try:
                        review_time = pd.to_datetime(review_time_str).to_pydatetime()
                    except:
                        pass
                
                withdrawal = CRMWithdrawals(
                    user_id=user_id,
                    request_id=request_id,
                    review_time=review_time,
                    trading_account=str(row_dict.get('Trading Account', '')).strip(),
                    withdrawal_amount=amount
                )
                
                db.session.add(withdrawal)
                added_count += 1
                
            except Exception as e:
                print(f"Error processing withdrawal row: {e}")
                continue
        
        db.session.commit()
        return {'added_rows': added_count, 'total_rows': len(rows)}
        
    except Exception as e:
        db.session.rollback()
        raise e

def process_crm_deposit_with_user(file_path, user_id, file_format='csv'):
    """Process CRM Deposit CSV data for a specific user"""
    try:
        if file_format.lower() == 'xlsx':
            data = pd.read_excel(file_path)
        else:
            data = pd.read_csv(file_path)
        
        if data.empty:
            raise ValueError("File is empty or invalid")
        
        headers = data.columns.tolist()
        rows = data.values.tolist()
        
        added_count = 0
        
        for row in rows:
            try:
                # Create row dictionary
                row_dict = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        row_dict[header.strip()] = row[i]
                
                request_id = str(row_dict.get('Request ID', '')).strip()
                if not request_id:
                    continue
                
                # Check if already exists
                existing = CRMDeposit.query.filter_by(request_id=request_id).first()
                if existing:
                    continue
                
                # Process trading amount (handle USC conversion)
                amount_val = str(row_dict.get('Trading Amount', '')).strip()
                amount = 0
                if amount_val:
                    import re
                    if 'USC' in amount_val:
                        parts = amount_val.split()
                        if len(parts) > 1:
                            number_part = re.sub(r'[^0-9.-]', '', parts[1])
                            amount = float(number_part) / 100 if number_part else 0
                        else:
                            amount = 0
                    else:
                        amount = float(re.sub(r'[^0-9.-]', '', amount_val)) if amount_val else 0
                
                # Parse request time
                request_time = None
                request_time_str = row_dict.get('Request Time', '')
                if request_time_str:
                    try:
                        request_time = pd.to_datetime(request_time_str).to_pydatetime()
                    except:
                        pass
                
                deposit = CRMDeposit(
                    user_id=user_id,
                    request_id=request_id,
                    request_time=request_time,
                    trading_account=str(row_dict.get('Trading Account', '')).strip(),
                    trading_amount=amount,
                    payment_method=str(row_dict.get('Payment Method', '')).strip(),
                    client_id=str(row_dict.get('Client ID', '')).strip(),
                    name=str(row_dict.get('Name', '')).strip()
                )
                
                db.session.add(deposit)
                added_count += 1
                
            except Exception as e:
                print(f"Error processing deposit row: {e}")
                continue
        
        db.session.commit()
        return {'added_rows': added_count, 'total_rows': len(rows)}
        
    except Exception as e:
        db.session.rollback()
        raise e

def upload_and_process_files():
    app = create_app()
    with app.app_context():
        # Get demo user
        user = User.query.filter_by(username='demo').first()
        if not user:
            print("Demo user not found. Please create a demo user first.")
            return
        
        # Define file mappings
        file_mappings = {
            '/app/m2p .csv': {
                'type': 'payment',
                'display_name': 'Payment Data (M2P)',
                'processor': process_payment_data_with_user
            },
            '/app/ib rebate.csv': {
                'type': 'ib_rebate', 
                'display_name': 'IB Rebate',
                'processor': process_ib_rebate_with_user
            },
            '/app/withdraw_20250804143053.csv': {
                'type': 'crm_withdrawals',
                'display_name': 'CRM Withdrawals', 
                'processor': process_crm_withdrawals_with_user
            },
            '/app/deposit_20250804143515.csv': {
                'type': 'crm_deposit',
                'display_name': 'CRM Deposit',
                'processor': process_crm_deposit_with_user
            }
        }
        
        # Create upload directory if it doesn't exist
        upload_folder = '/app/instance/uploads'
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
            print(f"Created upload directory: {upload_folder}")
        
        # Process each file
        for source_path, config in file_mappings.items():
            if not os.path.exists(source_path):
                print(f"Warning: File not found: {source_path}")
                continue
                
            file_type = config['type']
            display_name = config['display_name']
            processor = config['processor']
            
            print(f"\nProcessing {display_name}...")
            
            # Check if already uploaded for this user
            existing = UploadedFiles.query.filter_by(
                user_id=user.id, 
                file_type=file_type
            ).first()
            
            if existing:
                print(f"  File type {file_type} already exists for user {user.username}")
                continue
                
            # Copy file to upload directory
            filename = os.path.basename(source_path)
            safe_filename = f"{file_type}_{user.id}_{int(os.path.getmtime(source_path))}.csv"
            dest_path = os.path.join(upload_folder, safe_filename)
            
            shutil.copy2(source_path, dest_path)
            print(f"  Copied {filename} to {safe_filename}")
            
            # Record upload in database
            uploaded_file = UploadedFiles(
                user_id=user.id,
                file_type=file_type,
                filename=filename,
                file_path=dest_path
            )
            db.session.add(uploaded_file)
            
            try:
                # Process the file with user_id
                result = processor(dest_path, user.id, 'csv')
                uploaded_file.processed = True
                print(f"  Successfully processed: Added {result['added_rows']} rows")
                
            except Exception as e:
                print(f"  Error processing {display_name}: {str(e)}")
                uploaded_file.processed = False
        
        # Commit all changes
        db.session.commit()
        print(f"\nFile processing completed for user: {user.username}")
        
        # Display summary
        print("\nSummary of uploaded files:")
        user_files = UploadedFiles.query.filter_by(user_id=user.id).all()
        for file_record in user_files:
            status = "✓ Processed" if file_record.processed else "✗ Failed"
            print(f"  {file_record.file_type}: {file_record.filename} - {status}")

if __name__ == '__main__':
    upload_and_process_files()