import boto3
from botocore.exceptions import ClientError
import pandas as pd
from io import BytesIO
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

from src.config import AppConfig
from src.storage.s3_exceptions import (
    S3UploadError,
    S3BucketNotFoundError
)

class S3Writer:
    """
    Loads Zoom datasets (users, meetings, participants, recordings, etc.)
    into S3 as partitioned Parquet files:
    
    s3://bucket/<environment>/raw/<dataset_name>/year=YYYY/month=MM/day=DD/<dataset>.parquet
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.bucket = config.s3_bucket
        self.base_prefix = config.environment
        self.s3 = boto3.client("s3", region_name=config.aws_region)
    
    def _upload_parquet(self, df: pd.DataFrame, key: str):
        """Convert DF to Parquet and upload to S3."""
        buffer = BytesIO()
        df.to_parquet(buffer, index=False)
        buffer.seek(0)

        try:
            self.s3.upload_fileobj(buffer, self.bucket, key)
            logger.info(f"Uploaded Parquet file: s3://{self.bucket}/{key}")
        
        except ClientError as e:
            error_code = e.response['Error']['Code']

            if error_code == 'NoSuchBucket':
                raise S3BucketNotFoundError(f"Bucket not found: {self.bucket_name}")
            else:
                raise S3UploadError(f"S3 upload failed: {str(e)}")
        
        except Exception as e:
            logger.error(f"Upload failed: {str(e)}")


    def _load_generic(
        self,
        records: List[List[Dict[str, Any]]],
        dataset_name: str
    ):
        """
        Generic loader for any dataset type.
        Records: list of dicts from the extract steps.
        dataset_name: "users", "meetings", "participants", etc.
        timestamp_field: determines partition date (default: current UTC)
        """
        logger.info(f"Processing {dataset_name} dataset, {len(records)} chunks.")

        if not records:
            logger.warning(f"No {dataset_name} records to load.")
            return
        
        for count, record in enumerate(records):
            logger.info(f"Processing chunk {count}.")
            # Convert to DataFrame
            df = pd.DataFrame(record)

            # Build S3 key
            partition_time = datetime.now(timezone.utc)
            partition = f"year={partition_time.year}/month={partition_time.month:02d}/day={partition_time.day:02d}"
            key = f"{self.base_prefix}/raw/{dataset_name}/{partition}/{dataset_name}_{count}.parquet"

            self._upload_parquet(df, key)
            logger.info(f"Successfully processed chunk {count}.")
        
        logger.info(f"Successfully processed {dataset_name} dataset.")