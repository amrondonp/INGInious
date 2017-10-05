import web
import posixpath
import urllib
import os
import collections
import inginious.frontend.webapp.pages.api._api_page as api
from inginious.frontend.webapp.pages.utils import INGIniousPage
from inginious.frontend.webapp.pages.course_admin.utils import INGIniousAdminPage
from inginious.common.filesystems.local import LocalFSProvider
from inginious.common.course_factory import CourseNotFoundException, CourseUnreadableException, InvalidNameException
from .utils import convert_task_dict_to_sorted_list

_BASE_RENDERER_PATH = 'frontend/webapp/plugins/statistics'
_BASE_STATIC_FOLDER = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static')


class StaticResourcePage(INGIniousPage):
    def GET(self, path):
        path_norm = posixpath.normpath(urllib.parse.unquote(path))

        static_folder = LocalFSProvider(_BASE_STATIC_FOLDER)
        (method, mimetype_or_none, file_or_url) = static_folder.distribute(path_norm, False)

        if method == "local":
            web.header('Content-Type', mimetype_or_none)
            return file_or_url
        elif method == "url":
            raise web.redirect(file_or_url)

        raise web.notfound()


def statistics_course_admin_menu_hook(course):
    return "statistics", '<i class="fa fa-bar-chart" aria-hidden="true"></i> Course statistics'


class StatisticsAdminApi(api.APIAuthenticatedPage):
    def get_course_and_check_rights(self, course_id):
        try:
            course = self.course_factory.get_course(course_id)
        except (CourseNotFoundException, InvalidNameException, CourseUnreadableException):
            raise api.APIError(400, {"error": "Invalid course"})

        if not self.user_manager.has_staff_rights_on_course(course):
            raise api.APIError(400, {"error": "Invalid course"})

        return course

    def get_mandatory_parameter(self, parameters, parameter_name):
        if parameter_name not in parameters:
            raise api.APIError(400, {"error": parameter_name + " is mandatory"})

        return parameters[parameter_name]


class GradeCountStatisticsApi(StatisticsAdminApi):
    def _compute_grade_count_statistics(self, course_id):
        statistics_by_grade = self.database.user_tasks.aggregate([
            {"$match": {"courseid": course_id}},
            {
                "$group": {
                    "_id": {"grade": {"$ceil": "$grade"}, "task": "$taskid"},
                    "count": {"$sum": 1}
                }
            }
        ])

        task_id_to_statistics = collections.defaultdict(list)
        for element in statistics_by_grade:
            task_id = element["_id"]["task"]

            task_id_to_statistics[task_id].append({
                "grade": element["_id"]["grade"],
                "count": element["count"]
            })

        return task_id_to_statistics

    def API_GET(self):
        parameters = web.input()

        course_id = self.get_mandatory_parameter(parameters, 'course_id')
        course = self.get_course_and_check_rights(course_id)

        grade_count_statistics = self._compute_grade_count_statistics(course_id)
        statistics_by_grade_count = convert_task_dict_to_sorted_list(course, grade_count_statistics, 'grades',
                                                                     include_all_tasks=True)

        return 200, statistics_by_grade_count


class GradeDistributionStatisticsApi(StatisticsAdminApi):
    def _compute_grade_distribution_statistics(self, course_id):
        all_grades = self.database.user_tasks.find(
            {"courseid": course_id},
            {"taskid": 1, "grade": 1, "username": 1}
        )

        grouped_grades = collections.defaultdict(list)
        for item in all_grades:
            task_id = item["taskid"]

            grouped_grades[task_id].append(item["grade"])

        return grouped_grades

    def API_GET(self):
        parameters = web.input()

        course_id = self.get_mandatory_parameter(parameters, 'course_id')
        course = self.get_course_and_check_rights(course_id)

        grade_distribution_statistics = self._compute_grade_distribution_statistics(course_id)
        statistics_by_grade_distribution = convert_task_dict_to_sorted_list(course, grade_distribution_statistics,
                                                                            'grades', include_all_tasks=True)

        return 200, statistics_by_grade_distribution


class CourseAdminStatisticsPage(INGIniousAdminPage):
    def GET_AUTH(self, course_id):
        course, _ = self.get_course_and_check_rights(course_id)

        self.template_helper.add_javascript("https://cdnjs.cloudflare.com/ajax/libs/PapaParse/4.3.6/papaparse.min.js")
        self.template_helper.add_javascript("https://cdn.plot.ly/plotly-1.30.0.min.js")
        self.template_helper.add_javascript("https://cdn.jsdelivr.net/npm/lodash@4.17.4/lodash.min.js")
        self.template_helper.add_javascript("/static/statistics/js/statistics.js")
        self.template_helper.add_javascript("/static/statistics/js/course_admin_statistics.js")
        self.template_helper.add_css("/static/statistics/css/statistics.css")

        return (
            self.template_helper.get_custom_renderer(_BASE_RENDERER_PATH).course_admin_statistics(
                course)
        )
