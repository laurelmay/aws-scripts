import boto3


def create_session(profile_name=None) -> boto3.Session:
    """
    Create a boto3 session for a profile.
    """
    profile_args = {}
    if profile_name:
        profile_args["profile_name"] = profile_name
    return boto3.Session(**profile_args)
