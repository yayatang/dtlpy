Feature: Tasks repository create consensus task

  Background: Initiate Platform Interface and create a project
    Given Platform Interface is initialized as dlp and Environment is set according to git branch
    And I create a project by the name of "tasks_consensus"
    And I create a dataset with a random name
    And There are "10" items
    And I save dataset items to context

  @testrail-C4533547
  Scenario: Create consensus task with 100 percentage should success
    When I create Task
      | task_name=min_params | due_date=auto | assignee_ids=auto | consensus_percentage=auto | consensus_assignees=auto |
    Then I receive a task entity
    And Task has the correct attributes for type "annotation"
    And I expect Task created with "30" items

  @testrail-C4533547
  Scenario: Create consensus task with 50 percentage should success
    When I create Task
      | task_name=min_params | due_date=auto | assignee_ids=auto | consensus_percentage=50 | consensus_assignees=auto |
    Then I receive a task entity
    And Task has the correct attributes for type "annotation"
    And I expect Task created with "20" items