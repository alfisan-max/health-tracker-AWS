# Cloud Based Personal Health Tracker – Deployment Guide

Architecture: **S3 (site) → Cognito (login) → API Gateway (HTTP API) → Lambda → DynamoDB**
Use one AWS Region for everything (examples use `ap-south-1`, Mumbai). All services fit in the free tier.

## 1. DynamoDB – create two tables (capacity mode: On-demand)
| Table name | Partition key (String) | Sort key (String) |
|---|---|---|
| `Profiles` | `userId` | `profileId` |
| `HealthRecords` | `profileKey` | `recordDate` |

## 2. Cognito – user pool
1. Cognito → *Create user pool* → sign-in option **Email** → self-registration ON → verify email (Cognito default email sender is fine).
2. App client: type *Single-page application / Public client*, **no client secret**. Under authentication flows tick **ALLOW_USER_PASSWORD_AUTH**.
3. Note the **User Pool ID** (e.g. `ap-south-1_AbC123`) and the **Client ID**.

## 3. Lambda
1. Lambda → *Create function* → name `HealthTrackerApi`, runtime **Python 3.12**.
2. Paste `backend/lambda_function.py` into the editor → *Deploy*. (Configuration → General: set timeout to **15 s**, the first-login demo seeding needs a few seconds.)
3. Configuration → Environment variables (optional): `PROFILES_TABLE=Profiles`, `RECORDS_TABLE=HealthRecords`.
4. Configuration → Permissions → click the execution role → *Add inline policy* (JSON), replacing REGION and ACCOUNT_ID:
```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
 "Action":["dynamodb:GetItem","dynamodb:PutItem","dynamodb:DeleteItem","dynamodb:Query","dynamodb:BatchWriteItem"],
 "Resource":["arn:aws:dynamodb:REGION:ACCOUNT_ID:table/Profiles","arn:aws:dynamodb:REGION:ACCOUNT_ID:table/HealthRecords"]}]}
```

## 4. API Gateway – HTTP API
1. *Create API* → **HTTP API** → integration: Lambda `HealthTrackerApi`.
2. Routes (all pointing to that Lambda): `GET /profiles`, `GET /records`, `POST /records`, `DELETE /records/{date}`.
3. *Authorization* → create a **JWT authorizer**: Issuer `https://cognito-idp.REGION.amazonaws.com/USER_POOL_ID`, Audience = your **Client ID**, identity source `$request.header.Authorization`. Attach it to all four routes.
4. *CORS* → Allow origin: your S3 website URL (use `*` while testing), allow headers `authorization,content-type`, allow methods `GET,POST,DELETE,OPTIONS`.
5. Keep the auto-deploy `$default` stage; copy the **Invoke URL** (no trailing slash).

## 5. Front end on S3
1. Open `frontend/index.html` and edit `CFG` at the top: `region`, `clientId`, `api` (the Invoke URL).
2. S3 → create bucket → untick *Block all public access* → upload `index.html`.
3. Properties → *Static website hosting* → enable, index document `index.html`.
4. Permissions → bucket policy (replace BUCKET):
```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":"*","Action":"s3:GetObject","Resource":"arn:aws:s3:::BUCKET/*"}]}
```
5. Open the *Bucket website endpoint* URL, and add that origin to the API CORS setting from step 4.4.

## 6. Use it
Sign up → enter the emailed code → Confirm → Log in. On first login the Lambda automatically creates the demo profiles **Alex, Sarah, Rahul** with 30/14/30 days of synthetic data, so the dashboard and charts are populated immediately. Use the dropdown at the top to switch profiles.

## Troubleshooting
- **"USER_PASSWORD_AUTH flow not enabled"** → enable it on the app client (step 2.2).
- **CORS error in the browser console** → fix the allowed origin/headers in the API (step 4.4).
- **401 Unauthorized** → issuer/audience of the JWT authorizer must match your pool and client exactly.
- **500 error** → open Lambda → Monitor → CloudWatch logs; usually the IAM policy or table names/keys are wrong.
- To reset demo data: delete the user's items in both tables; the next login re-seeds.
