class FailureMessage:
    INVALID_LOGIN = 'Email or password is incorrect.'
    INVALID_CODE = 'That code is incorrect or has expired.'
    TOO_MANY_ATTEMPTS = 'Too many attempts. Please try again later.'
    RESEND_WAIT = 'Please wait a minute before requesting another code.'
    EXISTING_ACCOUNT = 'An account already exists with this email. Sign in instead.'
    EMAIL_FAILED = 'We could not send your code. Please try again shortly.'


class SuccessMessage:
    CODE_SENT = 'Check your inbox for a six-digit code.'
    VERIFIED = 'Your email is verified. Welcome to Nod.'
