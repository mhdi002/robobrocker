import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import PaymentData, IBRebate, CRMWithdrawals, CRMDeposit, AccountList, UploadedFiles
from flask_login import current_user
import uuid
import re

def detect_separator(line):
    """Detect CSV separator based on character count"""
    tab_count = line.count('\t')
    comma_count = line.count(',')
    semicolon_count = line.count(';')
    
    if tab_count >= comma_count and tab_count >= semicolon_count:
        return '\t'
    elif semicolon_count >= comma_count:
        return ';'
    return ','

def parse_date_flexible(date_str):
    """Parse dates in various formats"""
    if pd.isna(date_str) or not date_str:
        return None
    
    date_str = str(date_str).strip()
    
    # Try different date formats
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
        '%d.%m.%Y %H:%M:%S',
        '%d.%m.%Y',
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%Y',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None

def filter_unique_rows(existing_keys, new_rows, key_columns, data_headers):
    """Filter out duplicate rows based on key columns"""
    unique_rows = []
    
    for row in new_rows:
        # Create key from specified columns
        key_parts = []
        for idx in key_columns:
            if idx < len(row):
                val = str(row[idx] or '').strip().upper()
                key_parts.append(val)
        
        key = '|'.join(key_parts)
        
        if key and key not in existing_keys:
            existing_keys.add(key)
            unique_rows.append(row)
    
    return unique_rows

def process_payment_data(file_path, file_format='csv'):
    """Process payment CSV/XLSX data and store in database"""
    try:
        if file_format.lower() == 'xlsx':
            data = pd.read_excel(file_path)
        else:
            data = pd.read_csv(file_path)
        
        if data.empty or len(data) < 1:
            raise ValueError("File is empty or invalid")
        
        headers = data.columns.tolist()
        rows = data.values.tolist()
        
        # Define column mapping
        column_map = {
            'confirmed': 'Confirmed',
            'tx_id': 'Transaction ID', 
            'wallet_address': 'Wallet address',
            'status': 'Status',
            'type': 'Type',
            'payment_gateway': 'Payment gateway',
            'final_amount': 'Transaction amount',
            'final_currency': 'Transaction currency',
            'settlement_amount': 'Settlement amount',
            'settlement_currency': 'Settlement currency',
            'processing_fee': 'Processing fee',
            'price': 'Price',
            'comment': 'Comment',
            'payment_id': 'Payment ID',
            'created': 'Booked',
            'trading_account': 'Trading account',
            'balance_after': 'Balance after',
            'tier_fee': 'Tier fee'
        }
        
        added_count = 0
        
        for row in rows:
            try:
                # Create row dictionary
                row_dict = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        row_dict[header.strip()] = row[i]
                
                # Extract values
                tx_id = str(row_dict.get(column_map.get('tx_id', ''), '')).strip()
                status = str(row_dict.get(column_map.get('status', ''), '')).upper()
                pg_name = str(row_dict.get(column_map.get('payment_gateway', ''), '')).upper()
                tx_type = str(row_dict.get(column_map.get('type', ''), '')).upper()
                
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
                
                # Create new payment record
                payment = PaymentData(
                    user_id=current_user.id,
                    confirmed=row_dict.get(column_map.get('confirmed', '')),
                    tx_id=tx_id,
                    wallet_address=row_dict.get(column_map.get('wallet_address', '')),
                    status=status,
                    type=tx_type,
                    payment_gateway=row_dict.get(column_map.get('payment_gateway', '')),
                    final_amount=float(row_dict.get(column_map.get('final_amount', ''), 0) or 0),
                    final_currency=row_dict.get(column_map.get('final_currency', '')),
                    settlement_amount=float(row_dict.get(column_map.get('settlement_amount', ''), 0) or 0),
                    settlement_currency=row_dict.get(column_map.get('settlement_currency', '')),
                    processing_fee=float(row_dict.get(column_map.get('processing_fee', ''), 0) or 0),
                    price=float(row_dict.get(column_map.get('price', ''), 1) or 1),
                    comment=row_dict.get(column_map.get('comment', '')),
                    payment_id=row_dict.get(column_map.get('payment_id', '')),
                    created=parse_date_flexible(row_dict.get(column_map.get('created', ''))),
                    trading_account=row_dict.get(column_map.get('trading_account', '')),
                    correct_coin_sent=True,
                    balance_after=float(row_dict.get(column_map.get('balance_after', ''), 0) or 0),
                    tier_fee=float(row_dict.get(column_map.get('tier_fee', ''), 0) or 0),
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

def process_ib_rebate(file_path, file_format='csv'):
    """Process IB Rebate CSV/XLSX data"""
    try:
        if file_format.lower() == 'xlsx':
            data = pd.read_excel(file_path)
        else:
            data = pd.read_csv(file_path)
        
        if data.empty:
            raise ValueError("File is empty or invalid")
        
        headers = data.columns.tolist()
        rows = data.values.tolist()
        
        # Find required columns
        tx_id_idx = None
        rebate_idx = None
        rebate_time_idx = None
        
        for i, header in enumerate(headers):
            header_upper = header.strip().upper()
            if 'TRANSACTION ID' in header_upper:
                tx_id_idx = i
            elif 'REBATE' in header_upper and 'TIME' not in header_upper:
                rebate_idx = i
            elif 'REBATE TIME' in header_upper:
                rebate_time_idx = i
        
        if tx_id_idx is None or rebate_time_idx is None:
            raise ValueError("Required columns not found")
        
        added_count = 0
        
        for row in rows:
            try:
                if len(row) <= tx_id_idx:
                    continue
                
                tx_id = str(row[tx_id_idx] or '').strip()
                if not tx_id:
                    continue
                
                # Check if already exists
                existing = IBRebate.query.filter_by(transaction_id=tx_id).first()
                if existing:
                    continue
                
                rebate_value = float(row[rebate_idx] or 0) if rebate_idx is not None else 0
                rebate_time = parse_date_flexible(row[rebate_time_idx]) if rebate_time_idx is not None else None
                
                rebate = IBRebate(
                    user_id=current_user.id,
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

def process_crm_withdrawals(file_path, file_format='csv'):
    """Process CRM Withdrawals CSV/XLSX data"""
    try:
        if file_format.lower() == 'xlsx':
            data = pd.read_excel(file_path)
        else:
            # Detect separator for CSV
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline()
                separator = detect_separator(first_line)
            data = pd.read_csv(file_path, sep=separator)
        
        if data.empty:
            raise ValueError("File is empty or invalid")
        
        headers = data.columns.tolist()
        rows = data.values.tolist()
        
        # Find required columns (flexible matching)
        req_time_idx = None
        trading_account_idx = None
        amount_idx = None
        request_id_idx = None
        
        for i, header in enumerate(headers):
            header_upper = header.strip().upper()
            if 'REVIEW TIME' in header_upper:
                req_time_idx = i
            elif 'TRADING ACCOUNT' in header_upper:
                trading_account_idx = i
            elif 'WITHDRAWAL AMOUNT' in header_upper:
                amount_idx = i
            elif 'REQUEST ID' in header_upper:
                request_id_idx = i
        
        if None in [req_time_idx, trading_account_idx, amount_idx, request_id_idx]:
            raise ValueError("Required columns not found")
        
        added_count = 0
        
        for row in rows:
            try:
                if len(row) <= max(req_time_idx, trading_account_idx, amount_idx, request_id_idx):
                    continue
                
                request_id = str(row[request_id_idx] or '').strip()
                if not request_id:
                    continue
                
                # Check if already exists
                existing = CRMWithdrawals.query.filter_by(request_id=request_id).first()
                if existing:
                    continue
                
                # Process withdrawal amount (handle USC conversion)
                amount_val = str(row[amount_idx] or '').strip().upper()
                if 'USD' in amount_val:
                    amount = float(re.sub(r'[^0-9.-]', '', amount_val))
                elif 'USC' in amount_val:
                    raw_amount = float(re.sub(r'[^0-9.-]', '', amount_val))
                    amount = raw_amount / 100 if not pd.isna(raw_amount) else 0
                else:
                    amount = float(re.sub(r'[^0-9.-]', '', amount_val)) if amount_val else 0
                
                withdrawal = CRMWithdrawals(
                    user_id=current_user.id,
                    request_id=request_id,
                    review_time=parse_date_flexible(row[req_time_idx]),
                    trading_account=str(row[trading_account_idx] or '').strip(),
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

def process_crm_deposit(file_path, file_format='csv'):
    """Process CRM Deposit CSV/XLSX data"""
    try:
        if file_format.lower() == 'xlsx':
            data = pd.read_excel(file_path)
        else:
            data = pd.read_csv(file_path)
        
        if data.empty:
            raise ValueError("File is empty or invalid")
        
        headers = data.columns.tolist()
        rows = data.values.tolist()
        
        # Find required columns
        req_idx = None
        acc_idx = None
        amt_idx = None
        id_idx = None
        pay_method_idx = None
        client_id_idx = None
        name_idx = None
        
        for i, header in enumerate(headers):
            header_upper = header.strip().upper()
            if 'REQUEST TIME' in header_upper:
                req_idx = i
            elif 'TRADING ACCOUNT' in header_upper:
                acc_idx = i
            elif 'TRADING AMOUNT' in header_upper:
                amt_idx = i
            elif 'REQUEST ID' in header_upper:
                id_idx = i
            elif 'PAYMENT METHOD' in header_upper:
                pay_method_idx = i
            elif 'CLIENT ID' in header_upper:
                client_id_idx = i
            elif 'NAME' in header_upper and 'CLIENT' not in header_upper:
                name_idx = i
        
        if None in [req_idx, acc_idx, amt_idx, id_idx]:
            raise ValueError("Required columns not found")
        
        added_count = 0
        
        for row in rows:
            try:
                if len(row) <= max([idx for idx in [req_idx, acc_idx, amt_idx, id_idx] if idx is not None]):
                    continue
                
                request_id = str(row[id_idx] or '').strip()
                if not request_id:
                    continue
                
                # Check if already exists
                existing = CRMDeposit.query.filter_by(request_id=request_id).first()
                if existing:
                    continue
                
                # Process trading amount (handle USC conversion)
                amount_val = str(row[amt_idx] or '').strip()
                if 'USC' in amount_val:
                    parts = amount_val.split()
                    if len(parts) > 1:
                        number_part = re.sub(r'[^0-9.-]', '', parts[1])
                        amount = float(number_part) / 100 if number_part else 0
                    else:
                        amount = 0
                else:
                    amount = float(re.sub(r'[^0-9.-]', '', amount_val)) if amount_val else 0
                
                deposit = CRMDeposit(
                    user_id=current_user.id,
                    request_id=request_id,
                    request_time=parse_date_flexible(row[req_idx]),
                    trading_account=str(row[acc_idx] or '').strip(),
                    trading_amount=amount,
                    payment_method=str(row[pay_method_idx] or '').strip() if pay_method_idx is not None else '',
                    client_id=str(row[client_id_idx] or '').strip() if client_id_idx is not None else '',
                    name=str(row[name_idx] or '').strip() if name_idx is not None else ''
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

def process_account_list(file_path, file_format='csv'):
    """Process Account List CSV/XLSX data"""
    try:
        if file_format.lower() == 'xlsx':
            data = pd.read_excel(file_path)
        else:
            data = pd.read_csv(file_path, sep=';')
        
        if data.empty:
            raise ValueError("File is empty or invalid")
        
        # Remove description line if present
        if len(data) > 0 and 'METATRADER' in str(data.iloc[0, 0]).upper():
            data = data.iloc[1:]
        
        headers = data.columns.tolist()
        rows = data.values.tolist()
        
        # Find required columns
        login_idx = None
        name_idx = None
        group_idx = None
        
        for i, header in enumerate(headers):
            header_upper = str(header).strip().upper()
            if header_upper == 'LOGIN':
                login_idx = i
            elif header_upper == 'NAME':
                name_idx = i
            elif header_upper == 'GROUP':
                group_idx = i
        
        if None in [login_idx, name_idx, group_idx]:
            raise ValueError("Required columns (Login, Name, Group) not found")
        
        # Clear existing account list for this user
        AccountList.query.filter_by(user_id=current_user.id).delete()
        
        added_count = 0
        
        for row in rows:
            try:
                if len(row) <= max(login_idx, name_idx, group_idx):
                    continue
                
                login = str(row[login_idx] or '').strip()
                name = str(row[name_idx] or '').strip()
                group = str(row[group_idx] or '').strip()
                
                if not login:
                    continue
                
                is_welcome = group == "WELCOME\\Welcome BBOOK"
                
                account = AccountList(
                    user_id=current_user.id,
                    login=login,
                    name=name,
                    group=group,
                    is_welcome_bonus=is_welcome
                )
                
                db.session.add(account)
                added_count += 1
                
            except Exception as e:
                print(f"Error processing account row: {e}")
                continue
        
        db.session.commit()
        return {'added_rows': added_count, 'total_rows': len(rows)}
        
    except Exception as e:
        db.session.rollback()
        raise e