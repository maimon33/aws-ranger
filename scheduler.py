import time as Time

from crontab import CronTab
from datetime import time, date, timedelta, datetime

class Scheduler(object):
    def __init__(self, config_path, state_file):
        self.config_file = config_path
        self.state_file = state_file

    def start_of_day(self, day):
        try:
            start_hour = read_json_file_section(
                self.config_file, "Working Hours")["Start of working Day"]
            if start_hour > 23:
                Start_hour = 9
        except KeyError:
            start_hour = 9
        return  datetime.combine(day, time(int(start_hour), 00))

    def end_of_day(self, day):
        try:
            end_hour = read_json_file_section(
                self.config_file, "Working Hours")["End of working Day"]
            if end_hour > 23:
                end_hour = 18
        except KeyError:
            end_hour = 18
        return  datetime.combine(day, time(int(end_hour), 00))

    def next_weekday(self):
        workday = date.today() + timedelta(days=1)
        weekend = read_json_file_section(
            self.config_file, "Working Hours")["Last Day of the Week"]
        if weekend.lower() == "thursday":
            # 4 is Friday and 5 is Saturday
            weekend = [4, 5]
        else:
            # 5 is Saturday and 6 is Sunday
            weekend = [5, 6]

        while workday.weekday() in weekend:
            workday = workday + timedelta(days=1)
        else:
            return workday

    def end_of_week(self):
        today = datetime.now()
        last_day = read_json_file_section(
            self.config_file, "Working Hours")["Last Day of the Week"]
        if last_day.lower() == "thursday":
            # 3 for Thursday
            last_day = 3
            first_day = 6
        else:
            # 4 for Friday
            last_day = 4
            first_day = 0

        while today.weekday() > last_day and today.weekday() < first_day:
            today = today - timedelta(days=1)
        
        while today.weekday() > first_day:
            today = today + timedelta(days=1)
            
        end_of_week = self.end_of_day(today)
        return end_of_week
    
    def start_of_next_week(self):
        first_day = read_json_file_section(
            self.config_file, "Working Hours")["First Day of the Week"]
        if first_day.lower() == "sunday":
            # 6 for Sunday
            first_day = 6
        else:
            # 0 for Monday
            first_day = 0

        next_workday = self.next_weekday()
        while next_workday.weekday() != first_day:
            next_workday = next_workday + timedelta(days=1)
        start_of_week = self.start_of_day(next_workday)
        return start_of_week

    def get_next_action(self, action):
        now = datetime.now()
        take_five = now + timedelta(minutes=5)
        if self.start_of_day(self.next_weekday()) > now > self.end_of_week():
            return [action, take_five]
        elif now < self.start_of_day(self.next_weekday()):
            return [action, take_five]
        else:
            return ["start", self.start_of_day(self.next_weekday())]

    def get_next_task(self, policy, action):
        now = datetime.now()
        take_five = now + timedelta(minutes=5)
        if policy == "full":
            if self.start_of_day(now) < now < self.end_of_day(now):
                return [action, self.end_of_day(now)]
            else:
                return ["start", self.start_of_day(self.next_weekday())]
        elif policy == "nightly":
            if now < self.end_of_week() and now < self.end_of_day(now):
                return [action, self.end_of_day(now)]
            else:
                return [action, take_five]
        elif policy == "workweek":
            if self.end_of_day(now) < now < self.start_of_day(
                                                self.next_weekday()):
                return [action, take_five]
            else:
                return self.get_next_action(action)

    def get_schedule_section(self, policy, action):
        next_schedule_task = self.get_next_task(policy, action)
        schedule_info = {"policy": policy,
                         "Next Schedule Action": next_schedule_task[0],
                         "Next Schedule Time": next_schedule_task[1].strftime(
                             "%Y-%m-%d %H:%M:%S")}
        return schedule_info

    def update_schedule_section(self, policy, action, state_file):
        next_schedule_task = self.get_next_task(policy, action)
        next_job = self.get_next_action(action)
        schedule_info = {"Next Job Action": next_job[0],
                         "Next Job Time": next_job[1].strftime(
                             "%Y-%m-%d %H:%M:%S"),
                         "Next Schedule Action": next_schedule_task[0],
                         "Next Schedule Time": next_schedule_task[1].strftime(
                             "%Y-%m-%d %H:%M:%S"),
                         "policy": policy}
        update_dictionary(state_file, "_schedule", schedule_info)
        return schedule_info
    
    def compare_times(self, target_time):
        target_convert = datetime.strptime(target_time, '%Y-%m-%d %H:%M:%S')
        if target_convert < datetime.now():
            return True
        else:
            return False
    
    def cron_run(self, 
                 profile_name,
                 config_path, 
                 state_file, 
                 region, 
                 policy, 
                 execute, 
                 instances):
        
        if utils._find_duplicate_processes("ranger"):
            sys.exit()

        # Sets the schedule section and return the dict
        schedule_info = read_json_file_section(state_file, "_schedule")
        try:
            if schedule_info["Next Schedule Action"]:
                pass
        except KeyError:
            schedule_info = self.get_schedule_section(policy,
                                                      execute)
            update_dictionary(state_file, "_schedule", schedule_info)

        # Compare state file to current status
        update_instances_state_file(state_file, instances)

        # Fetch instances from state file and Remove _schedule section
        state_instances = read_json_file(state_file)
        state_instances.pop('_schedule', None)
        
        ranger = AWSRanger(profile_name=profile_name)

        if schedule_info["Next Schedule Action"] == "start":
            job_action = "stop"
            actionable_instances = create_short_instances_dict(state_instances, 
                                                               job_action)
            
            if len(actionable_instances[region]) > 0:
                schedule_info["Next Job's Target"] = actionable_instances
                update_dictionary(state_file, "_schedule", schedule_info)
            else:
                schedule_info["Next Job's Target"] = "None"
                update_dictionary(state_file, "_schedule", schedule_info)
            
            try:
                if self.compare_times(schedule_info["Next Job Time"]):
                    ranger.executioner(config_path, 
                                       state_file,
                                       actionable_instances, 
                                       action=job_action,
                                       cron=True)

                    for instance in actionable_instances[region]:
                        update_instance_state(state_file, 
                                              instance, 
                                              "ranger state", 
                                              "managed")
                    
                    next_job = self.get_next_action(job_action)
                    schedule_info.update({"Next Job Action": next_job[0],
                                          "Next Job Time": next_job[1].strftime(
                                              "%Y-%m-%d %H:%M:%S"),
                                          "Next Job's Target": "None"})
                    update_dictionary(state_file, "_schedule", schedule_info)
                else:
                    if len(actionable_instances[region]) > 0:
                        schedule_info.update(
                            {"Next Job's Target": actionable_instances})
                        update_dictionary(state_file, "_schedule", schedule_info)
                        
                        for instance in actionable_instances[region]:
                            update_instance_state(state_file, 
                                                  instance, 
                                                  "State", 
                                                  "running")
                    else:
                        schedule_info["Next Job's Target"] = "None"
                        update_dictionary(state_file, "_schedule", schedule_info)
            
            except KeyError:
                schedule_info.update({"Next Job Action": job_action,
                                      "Next Job's Target": actionable_instances,
                                      "Next Job Time": self.get_next_action(
                                          job_action)[1].strftime(
                                              "%Y-%m-%d %H:%M:%S")})
                update_dictionary(state_file, "_schedule", schedule_info)
            
        elif schedule_info["Next Schedule Action"] == "start":
            job_action = "start"
            actionable_instances = create_short_instances_dict(state_instances, 
                                                               job_action)
            if len(actionable_instances[region]) > 0:
                schedule_info["Next Job's Target"] = actionable_instances
                update_dictionary(state_file, "_schedule", schedule_info)
            else:
                schedule_info["Next Job's Target"] = "None"
                update_dictionary(state_file, "_schedule", schedule_info)
            
            try:
                if self.compare_times(schedule_info["Next Job Time"]):
                    ranger.executioner(config_path, 
                                       state_file,
                                       schedule_info["Next Job's Target"], 
                                       action=job_action,
                                       cron=True)
                    
                    for instance in actionable_instances[region]:
                        update_instance_state(state_file, 
                                              instance, 
                                              "ranger state", 
                                              "managed")
                    
                    next_job = self.get_next_action(job_action)
                    schedule_info.update({"Next Job Action": next_job[0],
                                          "Next Job Time": next_job[1].strftime(
                                              "%Y-%m-%d %H:%M:%S"),
                                          "Next Job's Target": "None"})
                    update_dictionary(state_file, "_schedule", schedule_info)
                else:
                    for instance in actionable_instances[region]:
                        update_instance_state(state_file, 
                                              instance, 
                                              "State", 
                                              "stopped")
                    print("not yet")
            except KeyError:
                print("Setting Job section")
                schedule_info.update({"Next Job Action": job_action,
                                      "Next Job's Target": actionable_instances,
                                      "Next Job Time": self.get_next_action(
                                          job_action)[1].strftime(
                                              "%Y-%m-%d %H:%M:%S")})
                update_dictionary(state_file, "_schedule", schedule_info)

        if schedule_info["Next Schedule Action"] == "terminate":
            job_action = "terminate"
            actionable_instances = create_short_instances_dict(state_instances, 
                                                               job_action)
            if len(actionable_instances[region]) > 0:
                schedule_info["Next Job's Target"] = actionable_instances
                update_dictionary(state_file, "_schedule", schedule_info)
            else:
                schedule_info["Next Job's Target"] = "None"
                update_dictionary(state_file, "_schedule", schedule_info)

            try:
                if self.compare_times(schedule_info["Next Job Time"]):
                    ranger.executioner(config_path, 
                                       state_file,
                                       schedule_info["Next Job's Target"], 
                                       action=job_action,
                                       cron=True)
                    
                    for instance in actionable_instances[region]:
                        remove_instance_from_state(state_file, region, instance)
                    
                    next_job = self.get_next_action(job_action)
                    schedule_info.update({"Next Job Action": next_job[0],
                                          "Next Job Time": next_job[1].strftime(
                                              "%Y-%m-%d %H:%M:%S"),
                                          "Next Job's Target": "None"})
                    update_dictionary(state_file, "_schedule", schedule_info)

            except KeyError:
                print("Setting Job section")
                schedule_info.update({"Next Job Action": job_action,
                                      "Next Job's Target": actionable_instances,
                                      "Next Job Time": self.get_next_action(
                                          job_action)[1].strftime(
                                              "%Y-%m-%d %H:%M:%S")})
                update_dictionary(state_file, "_schedule", schedule_info)

        try:
            if self.compare_times(schedule_info["Next Schedule Time"]):
                next_schedule_task = self.get_next_task(policy, execute)
                self.update_schedule_section(policy, 
                                             next_schedule_task[0], 
                                             state_file)
            else:
                next_schedule_task1 = self.get_next_task(policy, execute)
                schedule_info = {"Next Schedule Action": next_schedule_task1[0],
                                 "Next Schedule Time": next_schedule_task1[1].strftime(
                                     "%Y-%m-%d %H:%M:%S")}
                print(next_schedule_task1)
                next_schedule_task = self.get_next_task(policy, execute)
                schedule_info.update(
                    {"Next Schedule Action": next_schedule_task[0],
                     "Next Schedule Time": next_schedule_task[1].strftime(
                         "%Y-%m-%d %H:%M:%S")})
                print(schedule_info)
                update_dictionary(state_file, "_schedule", schedule_info)
        
        except KeyError:
            next_schedule_task = self.get_next_task(policy, execute)
            schedule_info.update(
                {"Next Schedule Action": next_schedule_task[0],
                 "Next Schedule Time": next_schedule_task[1].strftime(
                     "%Y-%m-%d %H:%M:%S")})
            update_dictionary(state_file, "_schedule", schedule_info)