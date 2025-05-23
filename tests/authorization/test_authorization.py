# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
# Client tests for SQL statement authorization

from __future__ import absolute_import, division, print_function
from getpass import getuser
import random
import threading
import time

import pytest

from tests.common.custom_cluster_test_suite import CustomClusterTestSuite
from tests.common.file_utils import assert_file_in_dir_contains
from tests.common.test_result_verifier import error_msg_equal
from tests.common.test_vector import HS2

PRIVILEGES = ['all', 'alter', 'drop', 'insert', 'refresh', 'select']
ADMIN = "admin"


class TestAuthorization(CustomClusterTestSuite):

  @classmethod
  def default_test_protocol(cls):
    return HS2

  @pytest.mark.execute_serially
  @CustomClusterTestSuite.with_args(
      "--server_name=server1 --authorization_policy_file=ignored_file",
      impala_log_dir="{deprecated_flags}", tmp_dir_placeholders=['deprecated_flags'],
      disable_log_buffering=True)
  def test_deprecated_flags(self):
    assert_file_in_dir_contains(self.impala_log_dir, "Ignoring removed flag "
                                                     "authorization_policy_file")

  @pytest.mark.execute_serially
  @CustomClusterTestSuite.with_args(
    impalad_args="--server-name=server1 --ranger_service_type=hive "
                 "--ranger_app_id=impala --authorization_provider=ranger "
                 "--min_privilege_set_for_show_stmts=select",
    catalogd_args="--server-name=server1 --ranger_service_type=hive "
                  "--ranger_app_id=impala --authorization_provider=ranger")
  def test_ranger_show_iceberg_metadata_tables(self, unique_name):
    unique_db = unique_name + "_db"
    tbl_name = "ice"
    full_tbl_name = "{}.{}".format(unique_db, tbl_name)
    non_existent_suffix = "_a"
    non_existent_tbl_name = full_tbl_name + non_existent_suffix
    priv = "select"
    user = getuser()
    query = "show metadata tables in {}".format(full_tbl_name)
    query_non_existent = "show metadata tables in {}".format(non_existent_tbl_name)
    admin_client = self.create_impala_client(user=ADMIN)
    user_client = self.create_impala_client(user=user)
    try:
      admin_client.execute("drop database if exists {} cascade".format(unique_db))
      admin_client.execute("create database {}".format(unique_db))
      admin_client.execute(
          "create table {} (i int) stored as iceberg".format(full_tbl_name))

      # Check that when the user has no privileges on the database, the error is the same
      # if we try an existing or a non-existing table.
      exc1_str = str(self.execute_query_expect_failure(user_client, query))
      exc2_str = str(self.execute_query_expect_failure(user_client, query_non_existent))
      assert error_msg_equal(exc1_str, exc2_str)
      assert "AuthorizationException" in exc1_str
      assert "does not have privileges to access"

      # Check that there is no error when the user has access to the table.
      admin_client.execute("grant {priv} on database {db} to user {target_user}".format(
          priv=priv, db=unique_db, target_user=user))
      self.execute_query_expect_success(user_client, query)
    finally:
      admin_client.execute(
          "revoke {priv} on database {db} from user {target_user}".format(
              priv=priv, db=unique_db, target_user=user))
      admin_client.execute("drop database if exists {} cascade".format(unique_db))

  @staticmethod
  def _verify_show_dbs(result, unique_name, visibility_privileges=PRIVILEGES):
    """ Helper function for verifying the results of SHOW DATABASES below.
    Only show databases with privileges implying any of the visibility_privileges.
    """
    for priv in PRIVILEGES:
      # Result lines are in the format of "db_name\tdb_comment"
      db_name = 'db_%s_%s\t' % (unique_name, priv)
      if priv != 'all' and priv not in visibility_privileges:
        assert db_name not in result.data
      else:
        assert db_name in result.data

  def _test_ranger_show_stmts_helper(self, unique_name, visibility_privileges):
    unique_db = unique_name + "_db"
    admin_client = self.create_impala_client(user=ADMIN)
    try:
      admin_client.execute("drop database if exists %s cascade" % unique_db)
      admin_client.execute("create database %s" % unique_db)
      for priv in PRIVILEGES:
        admin_client.execute("create database db_%s_%s" % (unique_name, priv))
        admin_client.execute("grant {0} on database db_{1}_{2} to user {3}"
                             .format(priv, unique_name, priv, getuser()))
        admin_client.execute("create table %s.tbl_%s (i int)" % (unique_db, priv))
        admin_client.execute("grant {0} on table {1}.tbl_{2} to user {3}"
                             .format(priv, unique_db, priv, getuser()))

      # Admin can still see all the databases and tables
      result = admin_client.execute("show databases")
      TestAuthorization._verify_show_dbs(result, unique_name)
      result = admin_client.execute("show tables in %s" % unique_db)
      assert result.data == ["tbl_%s" % p for p in PRIVILEGES]

      # Check SHOW DATABASES and SHOW TABLES using another username
      result = self.client.execute("show databases")
      TestAuthorization._verify_show_dbs(result, unique_name, visibility_privileges)
      result = self.client.execute("show tables in %s" % unique_db)
      # Only show tables with privileges implying any of the visibility privileges
      assert 'tbl_all' in result.data   # ALL can imply to any privilege
      for p in visibility_privileges:
        assert 'tbl_%s' % p in result.data
    finally:
      admin_client.execute("drop database if exists %s cascade" % unique_db)
      for priv in PRIVILEGES:
        admin_client.execute(
            "drop database if exists db_%s_%s cascade" % (unique_name, priv))

  @pytest.mark.execute_serially
  @CustomClusterTestSuite.with_args(
    impalad_args="--server-name=server1 --ranger_service_type=hive "
                 "--ranger_app_id=impala --authorization_provider=ranger "
                 "--min_privilege_set_for_show_stmts=select",
    catalogd_args="--server-name=server1 --ranger_service_type=hive "
                  "--ranger_app_id=impala --authorization_provider=ranger")
  def test_ranger_show_stmts_with_select(self, unique_name):
    self._test_ranger_show_stmts_helper(unique_name, ['select'])

  @pytest.mark.execute_serially
  @CustomClusterTestSuite.with_args(
    impalad_args="--server-name=server1 --ranger_service_type=hive "
                 "--ranger_app_id=impala --authorization_provider=ranger "
                 "--min_privilege_set_for_show_stmts=select,insert",
    catalogd_args="--server-name=server1 --ranger_service_type=hive "
                  "--ranger_app_id=impala --authorization_provider=ranger")
  def test_ranger_show_stmts_with_select_insert(self, unique_name):
    self._test_ranger_show_stmts_helper(unique_name, ['select', 'insert'])

  @pytest.mark.execute_serially
  @CustomClusterTestSuite.with_args(
    impalad_args="--server-name=server1 --ranger_service_type=hive "
                 "--ranger_app_id=impala --authorization_provider=ranger "
                 "--min_privilege_set_for_show_stmts=any",
    catalogd_args="--server-name=server1 --ranger_service_type=hive "
                  "--ranger_app_id=impala --authorization_provider=ranger")
  def test_ranger_show_stmts_with_any(self, unique_name):
    self._test_ranger_show_stmts_helper(unique_name, PRIVILEGES)

  @pytest.mark.execute_serially
  @CustomClusterTestSuite.with_args(
    impalad_args="--server-name=server1 --ranger_service_type=hive "
                 "--ranger_app_id=impala --authorization_provider=ranger "
                 "--num_check_authorization_threads=%d" % (random.randint(2, 128)),
    catalogd_args="--server-name=server1 --ranger_service_type=hive "
                  "--ranger_app_id=impala --authorization_provider=ranger")
  def test_num_check_authorization_threads_with_ranger(self, unique_name):
    self._test_ranger_show_stmts_helper(unique_name, PRIVILEGES)

  @CustomClusterTestSuite.with_args(
    impalad_args="--server-name=server1 --ranger_service_type=hive "
                 "--ranger_app_id=impala --authorization_provider=ranger "
                 "--use_local_catalog=true",
    catalogd_args="--server-name=server1 --ranger_service_type=hive "
                  "--ranger_app_id=impala --authorization_provider=ranger "
                  "--catalog_topic_mode=minimal")
  def test_local_catalog_show_dbs_with_transient_db(self, unique_name):
    """Regression test for IMPALA-13170"""
    # Starts a background thread to create+drop the transient db.
    # Use admin user to have create+drop privileges.
    unique_database = unique_name + "_db"
    admin_client = self.create_impala_client(user=ADMIN)
    stop = False

    def create_drop_db():
      while not stop:
        admin_client.execute("create database " + unique_database)
        # Sleep some time so coordinator can get the updates of it.
        time.sleep(0.1)
        if stop:
          break
        admin_client.execute("drop database " + unique_database)
    t = threading.Thread(target=create_drop_db)
    t.start()

    try:
      for i in range(100):
        self.execute_query("show databases")
        # Sleep some time so the db can be dropped.
        time.sleep(0.2)
    finally:
      stop = True
      t.join()
      admin_client.execute("drop database if exists " + unique_database)
