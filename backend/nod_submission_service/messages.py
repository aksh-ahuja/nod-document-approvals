class FailureMessage:
    INVALID_REVIEWER = 'Choose an active reviewer other than yourself.'
    NOT_FOUND = 'This submission is not available.'
    NOT_ASSIGNED = 'Only the assigned reviewer can make this decision.'
    ALREADY_DECIDED = 'This submission already has a decision. Refresh to see it.'
    REQUEST_CONFLICT = 'This request was already used for a different submission.'
    NOTE_REQUIRED = 'Add a reason so the submitter knows what needs fixing.'
    CONTENT_REQUIRED = 'Upload a document or enter its text.'
    CONTENT_CONFLICT = 'Choose a file or text, not both.'
    PREVIEW_UNAVAILABLE = 'The preview could not be generated. Try again or download the original.'
    UPLOAD_LEGACY = 'Upload your file first, then submit its upload ID.'
    LINK_EXPIRED = 'This file link has expired. Open the document again to get a new link.'


class SuccessMessage:
    SUBMITTED = 'Your document is with your reviewer.'
    DECIDED = 'Decision saved. Everyone is on the same page.'
