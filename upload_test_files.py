#!/usr/bin/env python3
"""
Script to automatically upload and process test CSV files for Stage 2 functionality
"""
import os
import shutil
from app import create_app, db
from app.models import User, UploadedFiles
from app.stage2_processing import (
    process_payment_data, process_ib_rebate, 
    process_crm_withdrawals, process_crm_deposit
)

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
                'processor': process_payment_data
            },
            '/app/ib rebate.csv': {
                'type': 'ib_rebate', 
                'display_name': 'IB Rebate',
                'processor': process_ib_rebate
            },
            '/app/withdraw_20250804143053.csv': {
                'type': 'crm_withdrawals',
                'display_name': 'CRM Withdrawals', 
                'processor': process_crm_withdrawals
            },
            '/app/deposit_20250804143515.csv': {
                'type': 'crm_deposit',
                'display_name': 'CRM Deposit',
                'processor': process_crm_deposit
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
                # Process the file
                result = processor(dest_path, 'csv')
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