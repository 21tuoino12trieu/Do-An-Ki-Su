import pyotp

secret = "REPLACE_WITH_LOCAL_SECRET"
totp = pyotp.TOTP(secret)

print(totp.now())