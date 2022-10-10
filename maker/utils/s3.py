# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import csv
import io

import boto3
from django.conf import settings


def upload_content_to_s3(content, filename):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.MAKER_AWS_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.MAKER_AWS_S3_SECRET_ACCESS_KEY,
    )
    s3.put_object(
        Body=content, Bucket=settings.MAKER_S3_FILE_STORAGE_BUCKET, Key=filename
    )


def download_file_object(key):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.MAKER_AWS_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.MAKER_AWS_S3_SECRET_ACCESS_KEY,
    )
    with io.BytesIO() as f:
        s3.download_fileobj(settings.MAKER_S3_FILE_STORAGE_BUCKET, key, f)
        return f.getvalue()


def download_csv_file_object(key):
    content = download_file_object(key)
    content = content.decode("utf-8")
    return csv.DictReader(content.splitlines())
