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

# where to put generated libraries
set(LIBRARY_OUTPUT_PATH "${BUILD_OUTPUT_ROOT_DIRECTORY}/workload_mgmt")

# where to put generated binaries
set(EXECUTABLE_OUTPUT_PATH "${BUILD_OUTPUT_ROOT_DIRECTORY}/workload_mgmt")

add_library(WorkloadMgmt
  workload-management.cc
  workload-management-flags.cc
)
add_dependencies(WorkloadMgmt gen-deps)

if (BUILD_WITH_NO_TESTS)
  return()
endif()

add_library(WorkloadMgmtTests STATIC
  workload-management-test.cc
  workload-management-fields-test.cc
)

add_dependencies(WorkloadMgmtTests gen-deps)

ADD_UNIFIED_BE_LSAN_TEST(workload-management-test WorkloadManagementTest.*:WorkloadManagementDeathTest.*)
ADD_UNIFIED_BE_LSAN_TEST(workload-management-fields-test WorkloadManagementFieldsTest.*)
