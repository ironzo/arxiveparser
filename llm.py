from prompt_library import *
from settings import model

def invoke(client, model, prompt, prefix, config):
    response = client.models.generate_content(
        model=model,
        contents = prompt+' '+prefix,
        config = config
    )
    return response
