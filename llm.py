from settings import model_name

def invoke(client, model, prompt, prefix, config):
    response = client.models.generate_content(
        model=model_name,
        contents = prompt+' '+prefix,
        config = config
    )
    return response
