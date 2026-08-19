from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def append_to_doc(creds, doc_id: str, content: str):
    try:
        service = build("docs", "v1", credentials=creds)
        
        doc = service.documents().get(documentId=doc_id).execute()
        
        # The document body has a content list.
        # The last element in the content list has the maximum endIndex.
        # The very last index is the document end newline, which we cannot insert at.
        # We must insert at endIndex - 1.
        body = doc.get('body')
        content_elements = body.get('content')
        end_index = content_elements[-1].get('endIndex') - 1
        
        requests = [
            {
                'insertText': {
                    'location': {
                        'index': end_index,
                    },
                    'text': content
                }
            }
        ]
        
        result = service.documents().batchUpdate(
            documentId=doc_id, body={'requests': requests}).execute()
        
        return {"status": "success", "result": result}
    except HttpError as err:
        return {"status": "error", "error": str(err)}
