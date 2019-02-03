

def save_to_file(sess, resp):
    filename = resp.request.path_url.split("/", 1)[1]
    with open('/tmp/%s' % filename, 'wb') as fd:
        for chunk in resp.iter_content(chunk_size=128):
            fd.write(chunk)