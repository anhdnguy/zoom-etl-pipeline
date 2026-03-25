class S3Error (Exception):
    """Base exception for all S3 errors"""

class S3UploadError(S3Error):
    """Failed to upload recording to S3"""
    pass

class S3BucketNotFoundError(S3Error):
    """S3 bucket does not exist"""
    pass