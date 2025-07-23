# MIDAS Secrets Directory

This directory contains sensitive configuration files for the MIDAS application.

## Required Files

Create the following files with your secure values:

### 1. postgres_password.txt
Contains the PostgreSQL database password. No newlines or extra spaces.
```
your_secure_postgres_password_here
```

### 2. app_secret_key.txt
Contains the application secret key for session management.
```
your_secure_app_secret_key_here
```

## Generating Secure Secrets

### On Windows PowerShell:
```powershell
# Generate a secure password
-join ((65..90) + (97..122) + (48..57) | Get-Random -Count 32 | % {[char]$_}) | Out-File -NoNewline postgres_password.txt

# Generate a secure app key
-join ((65..90) + (97..122) + (48..57) | Get-Random -Count 64 | % {[char]$_}) | Out-File -NoNewline app_secret_key.txt
```

### Using Python:
```python
import secrets
import string

# Generate secure password
alphabet = string.ascii_letters + string.digits
password = ''.join(secrets.choice(alphabet) for i in range(32))
with open('postgres_password.txt', 'w') as f:
    f.write(password)

# Generate secure app key
app_key = secrets.token_urlsafe(64)
with open('app_secret_key.txt', 'w') as f:
    f.write(app_key)
```

## Security Notes

1. **Never commit these files to version control**
2. **Set appropriate file permissions** (read-only for the Docker user)
3. **Rotate secrets regularly**
4. **Use Docker secrets in production** instead of bind mounting files
5. **Consider using a secrets management system** like HashiCorp Vault for production