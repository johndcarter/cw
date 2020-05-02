import shlex
from subprocess import Popen, PIPE
from os import getcwd, chdir

import unittest


# reference: https://stackoverflow.com/a/21000308/459082
def get_exitcode_stdout_stderr(cmd):
    """
    Execute the external command and get its exitcode, stdout and stderr.
    """
    args = shlex.split(cmd)

    proc = Popen(args, stdout=PIPE, stderr=PIPE)
    std_out, std_err = proc.communicate()
    exit_code = proc.returncode
    #
    return exit_code, std_out, std_err


# return format:
#    { file_name : (inserts, delete) }
def get_insert_deletes_from_git_sha(directory_of_repo, sha) -> dict:
    return_dict = {}
    cwd = getcwd()
    chdir(directory_of_repo)
    exit_code, std_out, _ = get_exitcode_stdout_stderr(f'git show {sha} --numstat --format=""')
    std_out_string = std_out.decode('utf-8').strip()
    lines = std_out_string.split('\n')

    for line in lines:
        tokens = line.split('\t')
        if len(tokens) == 3:
            return_dict[tokens[2]] = (tokens[0], tokens[1])

    chdir(cwd)
    return return_dict


class TestExecuteCommand(unittest.TestCase):
    def test_pwd(self):
        ec, so, se = get_exitcode_stdout_stderr('pwd')
        self.assertEqual(ec, 0)
        self.assertGreater(len(str(so)), 0)

    def test_git_show(self):
        print(get_insert_deletes_from_git_sha('/Users/johncarter/development/uswish',
                                              '5c41a0cbd397bbdf72e31360b7ac1c76a2c307b9'))
