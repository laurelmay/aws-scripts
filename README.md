# helpful_aws_scripts

A collection of scripts that are useful for interacting with AWS.

## Dependencies

The scripts in this project likely only work with the newest version of Python.
Install dependencies from the `requirements.txt` file.

## Scripts

There are a variety of scripts in this repository and there isn't really a
consistent structure to them. All scripts provide a `--help` option with
detailed information on the options available for that script.

### all_open_prs.py

This script lists all the open pull requests in AWS CodeCommit.

### aws_ip_info.py

Given an IP address or hostname looks up the information on the underlying AWS
IP address. This provides the information available through the
[AWS IP Ranges](https://docs.aws.amazon.com/general/latest/gr/aws-ip-ranges.html)
data file.

### bitbucket_to_codecommit.py

This makes an attempt to perform a migration from a self-hosted BitBucket Server
(or Datacenter) installation to AWS CodeCommit. This creates the repositories
via the CodeCommit API, clones the repositories from BitBucket, and mirrors them
to CodeCommit. This should be used for a single migration; it does not support
continuous synchronization.

### cfn_tag_support.py

This a script to parse the
[CloudFormation specification](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-resource-specification-format.html)
to find all resources that support a given property (by default, `Tags`). This
defaults to checking in `us-east-1` but any region can be provided to check since
resource and property availability may vary by region.

### clean_log_groups.py

This shows information about existing CloudWatch Logs Log Groups and assists in
deleting them in batches.

### clean_streams.py

This shows information about Log Stream in a CloudWatch Logs Log Group. This
supports deleting streams in batches.

### create-govcloud-account.py

This script creates an AWS GovCloud (US) account via AWS Organizations. In order to
effectively leverage this script, it is necessary to run this script in the management
account for the Organization in the commercial partition and to have already manually
gone through the process to have a GovCloud (US) account linked to the management account.

### deregister_lost_instances.py

This helps deregister managed instances from AWS Systems Manager that have entered a
`ConnectionLost` status.

### dynamodb_item_import.py

Use this script to load a JSON file into DynamoDB via `dynamodb:PutItem` API calls.
This does not perform any sort of transformation and uses the low-level `boto3` client.

### find-ip-addrs.py

This script will list available IP addresses in one or more subnets in an AWS account
that match the given subnet ID or subnet name (or all subnets in the account if neither
is provided).

This script may be useful in environments where static address allocation is used
without coherent IPAM.

### rotate-keys.py

Helps rotate the IAM Access Keys for an IAM User. This creates a new access key,
updates the `~/.aws/credentials` file, and deletes the old access key.

### stack_destroy.py

Delete all CloudFormation stacks in an AWS account. This will disable termination
protection for all stacks as well. Rather than using waiters, this performs more of
a busy looping; executing a `DeleteStack` operation on all stacks at a given interval.
It is possible to ignore specific stacks. A `role-arn` flag is available in the
event that the role used to create the stack does not have sufficient permissions to
delete the resources in the stack.

### stacks_using_stack.py

This lists all CloudFormation stacks that use any of the exports of the given stack.
This may help determine dependencies between CloudFormation stacks.

## License

This project is licensed under the terms of the MIT License. For more information,
see the [LICENSE](LICENSE) file.

## TODO

It is an eventual goal to rework the packaging for this script to leverage `click`'s
command groups feature and create a cohesive CLI and a package that can meaningfully
be installed and used. In the interim, create a virtualenv in which all dependencies
from `requirement.txt` can be used.