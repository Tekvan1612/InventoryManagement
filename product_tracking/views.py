import json
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.db import connection, transaction, DatabaseError
from django.contrib.auth.models import User
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
import os

from django.views.decorators.csrf import csrf_exempt
from psycopg2 import IntegrityError
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)


# Create your views here.
@login_required
def index(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/index.html', {'username': username})


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not (username and password):
            messages.error(request, 'Username and password are required.')
            return render(request, 'product_tracking/page-login.html')

        user = authenticate_user(username, password)

        if user is not None:
            login(request, user)
            return redirect('index')
        else:
            return render(request, 'product_tracking/page-login.html',
                          {'error_message': 'Invalid username or password'})
    else:
        return render(request, 'product_tracking/page-login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def authenticate_user(username, password):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT validate_user(%s, %s, TRUE)", [username, password])
            if cursor.fetchone()[0]:
                try:
                    user = User.objects.get(username=username)
                except User.DoesNotExist:
                    logger.warning(
                        f"User '{username}' authenticated via PostgreSQL function but does not exist in Django.")
                    return None
                return user
            else:
                logger.info(f"Failed authentication attempt for user '{username}'.")
                return None
    except Exception as e:
        logger.exception("Error occurred during user authentication.")
        return None


def footer(request):
    return render(request, 'product_tracking/footer.html')


def head(request):
    return render(request, 'product_tracking/head.html')


def header(request):
    return render(request, 'product_tracking/header.html')


def navheader_view(request):
    return render(request, 'product_tracking/navheader.html')


def sidebar(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/sidebar.html', {'username': username})


def app_calender(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/app-calender.html', {'username': username})


def contact(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/contacts.html', {'username': username})


def employee(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/employee.html', {'username': username})


def performance(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/performance.html', {'username': username})


def task(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/jobs.html', {'username': username})


@login_required
def add_category(request):
    if request.method == 'POST':
        category_name = request.POST.get('category_name')
        description = request.POST.get('description')
        status = request.POST.get('status') == '1'
        created_by = request.user.id
        created_date = datetime.now()

        try:
            with connection.cursor() as cursor:
                # Check if the category already exists
                cursor.execute("SELECT COUNT(*) FROM master_category WHERE category_name = %s", [category_name])
                category_count = cursor.fetchone()[0]

                if category_count > 0:
                    return JsonResponse({'success': False, 'message': 'Category Already Exists!'})

                # If the category doesn't exist, insert it
                cursor.execute(
                    "SELECT add_category(%s, %s, %s, %s, %s);",
                    [category_name, description, status, created_by, created_date]
                )
            return JsonResponse({'success': True})
        except Exception as e:
            print("An unexpected error occurred:", e)
            return JsonResponse({'success': False, 'message': 'An unexpected error occurred'})
    else:
        username = None
        if request.user.is_authenticated:
            username = request.user.username
        return render(request, 'product_tracking/performance1.html', {'username': username})


@login_required
def category_list(request):
    page = int(request.GET.get('page', 1))
    page_size = 10
    offset = (page - 1) * page_size

    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM master_category")
        total_items = cursor.fetchone()[0]

        cursor.execute("SELECT * FROM get_category_details() LIMIT %s OFFSET %s", [page_size, offset])
        rows = cursor.fetchall()

    category_listing = []
    for row in rows:
        created_date = row[5].strftime('%d-%m-%Y')
        category_listing.append({
            'category_id': row[0],
            'category_name': row[1],
            'category_description': row[2],
            'status': row[3],
            'created_by': row[4],
            'created_date': created_date
        })

    return JsonResponse({
        'categories': category_listing,
        'total_items': total_items,
        'current_page': page
    }, safe=False)


@login_required
@csrf_exempt
def update_category(request, category_id):
    if request.method == 'POST':
        print('Received POST request to update category details')

        # Extract the form data
        category_name = request.POST.get('categoryName')
        category_description = request.POST.get('categoryDescription', '')
        status = request.POST.get('statusText') == 'true' or request.POST.get(
            'statusText') == 'True' or request.POST.get('statusText') == '1'

        print('Received data:', {
            'category_id': category_id,
            'category_name': category_name,
            'category_description': category_description,
            'status': status,
        })

        try:
            with connection.cursor() as cursor:
                cursor.callproc('update_category', [category_id, category_name, category_description, status])
                updated_category_id = cursor.fetchone()[0]
                print(updated_category_id)
            return JsonResponse(
                {'success': True, 'message': 'Category details updated successfully',
                 'updated_category_id': updated_category_id})
        except Exception as e:
            return JsonResponse({'success': False, 'message': 'Failed to update category details', 'exception': str(e)})
    else:
        return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
def delete_category(request, category_id):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.callproc('delete_category', [category_id])
            return JsonResponse({'message': 'Category deleted successfully', 'category_id': category_id})
        except Exception as e:
            logger.error(f'Failed to delete category with ID {category_id}: {e}', exc_info=True)
            return JsonResponse({'error': 'Failed to delete category', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)


def sub_category(request):
    return render(request, 'product_tracking/sub-performance1.html')


@login_required
def category_dropdown(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT category_id, category_name FROM get_category_details()')
            categories = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
            print('Categories fetched successfully:', categories)
            return JsonResponse({'categories': categories}, safe=False)
    except Exception as e:
        # Handle exceptions, maybe log the error for debugging
        print("Error fetching categories:", e)
        return JsonResponse({'categories': []})


@login_required
def add_sub_category(request):
    if request.method == 'POST':
        category_id = request.POST.get('category_name')
        subcategory_name = request.POST.get('subcategory_name')
        status = request.POST.get('status')
        created_by = request.user.id
        created_date = datetime.now()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT add_sub_category(%s, %s, %s, %s, %s);",
                    [category_id, subcategory_name, status, created_by, created_date]
                )
                return JsonResponse({'success': True})
        except Exception as e:
            if 'Subcategory already exists' in str(e):
                return JsonResponse({'success': False, 'message': 'Sub Category Already Exists!'})
            else:
                print("An unexpected error occurred:", e)
                return JsonResponse({'success': False, 'message': 'An unexpected error occurred'})
    else:
        username = None
        if request.user.is_authenticated:
            username = request.user.username
        categories = subcategory_list(request)  # Function to get all categories
        return render(request, 'product_tracking/sub-performance1.html',
                      {'username': username, 'categories': categories})


@login_required
def subcategory_list(request, category_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM get_sub(%s)", [category_id])
        rows = cursor.fetchall()

    subcategory_listing = []
    for row in rows:
        created_date = row[5].strftime('%d-%m-%Y')
        subcategory_listing.append({
            'id': row[0],
            'category_name': row[1],
            'name': row[2],
            'status': row[3],
            'created_by': row[4],
            'created_date': created_date
        })

    context = {
        'subcategories': json.dumps(subcategory_listing),  # Ensure JSON is correctly formatted
        'category_id': category_id
    }
    return render(request, 'product_tracking/sub-performance1.html', context)


@login_required
def update_subcategory(request, id):
    if request.method == 'POST':
        print('Received POST request to update sub category details')

        # Extract the form data
        name = request.POST.get('categoryName')
        # status = request.POST.get('statusText')

        print('Received data:', {
            'id': id,
            'name': name,

        })

        try:
            with connection.cursor() as cursor:
                cursor.callproc('update_subcategory', [id, name])
                updated_category_id = cursor.fetchone()[0]
                print(updated_category_id)
            return JsonResponse(
                {'message': 'Sub Category details updated successfully', 'updated_category_id': updated_category_id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to update sub category details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


@login_required
def delete_subcategory(request, id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.callproc('delete_subcategory', [id])
            return JsonResponse({'message': 'Category deleted successfully', 'category_id:': id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to delete category', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def add_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        status = request.POST.get('status') == '1'
        modules = request.POST.getlist('modules')
        created_by = int(request.user.id)
        created_date = datetime.now()

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT add_user(%s, %s, %s, %s, %s, %s);",
                [username, password, status, modules, created_by, created_date]
            )
            user_id = cursor.fetchone()[0]
            print(user_id)
        return redirect('add_user')
    else:
        # Fetch employee names from the employee table
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM employee")
            employees = cursor.fetchall()

        employee_names = [employee[0] for employee in employees]

        username = None
        if request.user.is_authenticated:
            username = request.user.username
        return render(request, 'product_tracking/user.html', {'username': username, 'employee_names': employee_names})


@login_required
def user_list(request):
    print('Received data:')
    user_listing = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM getuser()")
            rows = cursor.fetchall()
            print("fetched user list")

            for row in rows:
                created_date_time = row[6].strftime('%d-%m-%Y')
                user_listing.append({
                    'user_id': row[0],
                    'user_name': row[1],
                    'password': row[2],
                    'status': row[3],
                    'modules': row[4] if row[4] else [],  # Ensure modules is a list
                    'created_by': row[5],
                    'created_date_time': created_date_time
                })
    except Exception as e:
        print("Error fetching user list:", e)

    # Implement pagination
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 10)
    paginator = Paginator(user_listing, page_size)
    page_obj = paginator.get_page(page)

    response = {
        'data': list(page_obj.object_list),
        'total_items': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number,
    }

    return JsonResponse(response)


@login_required
def update_user(request, user_id):  # noqa
    if request.method == 'POST':
        user_id = request.POST.get('userId')
        user_name = request.POST.get('username')
        password = request.POST.get('password')
        status = request.POST.get('statusText')
        modules = request.POST.getlist('modules[]')

        print('Received data:', user_id, user_name, password, status, modules)

        try:
            with connection.cursor() as cursor:
                cursor.callproc('update_user', [user_id, user_name, password, status, modules])
                cursor.execute("COMMIT;")
            return JsonResponse({'message': 'User details updated successfully', 'user_id': user_id})
        except Exception as e:
            return JsonResponse({'error': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


@login_required
def delete_user(request, id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.callproc('deleteuser', [id])
            return JsonResponse({'message': 'User deleted successfully', 'User_id:': id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to delete User', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def add_employee(request):
    if request.method == 'POST':
        try:
            employee_id = int(request.POST.get('employee_id').strip())
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid employee ID. Please enter a valid integer.'}, status=400)

        name = request.POST.get('name')
        email = request.POST.get('email')
        designation = request.POST.get('designation')
        try:
            mobile_no = int(request.POST.get('mobile_no').strip())
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid mobile number. Please enter a valid integer.'}, status=400)

        gender = request.POST.get('gender')
        joining_date = request.POST.get('joining_date')
        dob = request.POST.get('dob')
        reporting_id = request.POST.get('reporting')
        p_address = request.POST.get('p_address')
        c_address = request.POST.get('c_address')
        country = request.POST.get('country')
        state = request.POST.get('state')
        status = request.POST.get('status').lower() == 'true'
        created_by = request.user.id
        created_date = datetime.now()
        profile_photo = request.FILES.get('profile_photo')
        attachment_images = request.FILES.getlist('attachments[]')

        # Validate profile photo size
        if profile_photo:
            if profile_photo.size < 4000 or profile_photo.size > 12288:  # 5KB to 12KB
                return JsonResponse({'error': 'Profile photo size must be between 5KB and 12KB.'}, status=400)

        profile_pic_dir = os.path.join(settings.MEDIA_ROOT, 'profilepic')
        uploads_dir = os.path.join(settings.MEDIA_ROOT, 'uploads')
        os.makedirs(profile_pic_dir, exist_ok=True)
        os.makedirs(uploads_dir, exist_ok=True)

        # Check for duplicates
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM employee
                WHERE employee_id = %s OR email = %s OR mobile_no = %s
            """, [employee_id, email, mobile_no])
            duplicate_count = cursor.fetchone()[0]

        if duplicate_count > 0:
            return JsonResponse({'error': 'Employee with this ID, email, or mobile number already exists.'}, status=400)

        # Fetch reporting name
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM employee WHERE id = %s", [reporting_id])
            reporting_name = cursor.fetchone()
            if reporting_name is None:
                return JsonResponse({'error': 'Invalid reporting ID.'}, status=400)
            reporting_name = reporting_name[0]

        # Process profile photo
        profile_photo_path = None
        if profile_photo:
            profile_photo_path = os.path.join(profile_pic_dir, profile_photo.name)
            with open(profile_photo_path, 'wb') as f:
                for chunk in profile_photo.chunks():
                    f.write(chunk)

        # Process attachment images
        image_paths = [None, None]
        for i, image in enumerate(attachment_images[:2]):
            if image:
                image_path = os.path.join(uploads_dir, image.name)
                with open(image_path, 'wb') as f:
                    for chunk in image.chunks():
                        f.write(chunk)
                image_paths[i] = image_path

        # Call the stored procedure/function
        try:
            with connection.cursor() as cursor:
                cursor.callproc('add_employee', [
                    employee_id, name, email, designation, mobile_no, gender,
                    joining_date, dob, reporting_name, p_address, c_address, country, state,
                    status, created_by, created_date,
                    profile_photo_path, image_paths[0], image_paths[1]
                ])
        except IntegrityError as e:
            return JsonResponse({'error': 'Integrity error occurred: ' + str(e)}, status=400)

        return JsonResponse({'success': 'Employee added successfully'}, status=200)

    return render(request, 'product_tracking/employee.html', {'employees': get_all_employees()})


def get_all_employees():
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM employee")
        employees = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
    return employees


@login_required
def employee_dropdown(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM employee")
        employees = cursor.fetchall()
        employee_list = [{'id': emp[0], 'name': emp[1]} for emp in employees]

    return JsonResponse({'employees': employee_list})


@login_required
def employee_list(request):
    employee_listing = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM get_employee_details()")
            rows = cursor.fetchall()
            for index, row in enumerate(rows):
                created_date = row[16].strftime('%Y-%m-%d') if row[16] else None
                joining_date = row[7].strftime('%Y-%m-%d') if row[7] else None
                dob = row[8].strftime('%Y-%m-%d') if row[8] else None

                image_path = row[17]
                image_url = None
                if image_path:
                    image_relative_path = os.path.relpath(image_path, settings.MEDIA_ROOT)
                    image_url = os.path.join(settings.MEDIA_URL, image_relative_path).replace('\\', '/')
                else:
                    image_url = os.path.join(settings.MEDIA_URL, 'profilepic/default.jpg')

                logger.debug(f"Employee row: {row}")

                employee_listing.append({
                    'sr_no': index + 1,
                    'id': row[0],
                    'employee_id': row[1],
                    'name': row[2],
                    'email': row[3],
                    'mobile_no': row[5],
                    'designation': row[4],
                    'gender': row[6],
                    'joining_date': joining_date,
                    'dob': dob,
                    'reporting': row[9],
                    'p_address': row[10],
                    'c_address': row[11],
                    'country': row[12],
                    'state': row[13],
                    'status': row[14],
                    'created_by': row[15],
                    'created_date': created_date,
                    'profile_pic': image_url,
                    'attachments': row[18],  # This should be a list of character varying
                    'attachment_ids': row[19]  # This should be a list of integers
                })
    except Exception as e:
        logger.error("An error occurred while fetching the employee list: %s", str(e), exc_info=True)
        return JsonResponse({'error': 'An error occurred while fetching the employee list: ' + str(e)}, status=500)

    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 10)
    paginator = Paginator(employee_listing, page_size)
    page_obj = paginator.get_page(page)

    response = {
        'data': list(page_obj.object_list),
        'total_items': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number,
    }

    return JsonResponse(response)


@csrf_exempt
@login_required
def delete_attachment(request):
    if request.method == 'POST':
        attachment_id = request.POST.get('attachment_id')

        if attachment_id:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM employee_images WHERE id = %s", [attachment_id])
                return JsonResponse({'success': 'Attachment deleted successfully'})
            except Exception as e:
                return JsonResponse({'error': 'Error deleting attachment: ' + str(e)}, status=400)
        else:
            return JsonResponse({'error': 'Invalid attachment ID'}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
@login_required
def modify_employee(request):
    if request.method == 'POST':
        operation = request.POST.get('operation')
        emp_id = request.POST.get('id')

        if not emp_id or not emp_id.isdigit():
            return JsonResponse({'error': 'Invalid employee ID'}, status=400)

        emp_id = int(emp_id)

        if operation == 'update':
            emp_employee_id = request.POST.get('employee_id') or None
            emp_name = request.POST.get('name') or None
            emp_email = request.POST.get('email') or None
            emp_designation = request.POST.get('designation') or None
            emp_mobile_no = request.POST.get('mobile_no') or None
            emp_gender = request.POST.get('gender') or None
            emp_joining_date = request.POST.get('joining_date') or None
            emp_dob = request.POST.get('dob') or None
            emp_reporting = request.POST.get('reporting') or None
            emp_p_address = request.POST.get('p_address') or None
            emp_c_address = request.POST.get('c_address') or None
            emp_country = request.POST.get('country') or None
            emp_state = request.POST.get('state') or None
            emp_status = request.POST.get('status') == 'true'
            removed_profile_pic = request.POST.get('removed_profile_pic') == 'true'

            try:
                removed_attachments = request.POST.get('removed_attachments')
                removed_attachments = json.loads(removed_attachments) if removed_attachments else []

                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT modify_employee(
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                            """,
                            [
                                operation,
                                emp_id,
                                int(emp_employee_id) if emp_employee_id else None,
                                emp_name,
                                emp_email,
                                emp_designation,
                                int(emp_mobile_no) if emp_mobile_no else None,
                                emp_gender,
                                emp_joining_date,
                                emp_dob,
                                emp_reporting,
                                emp_p_address,
                                emp_c_address,
                                emp_country,
                                emp_state,
                                emp_status
                            ]
                        )

                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1 FROM employee WHERE id = %s", [emp_id])
                        if cursor.fetchone() is None:
                            raise Exception(f"Employee ID {emp_id} does not exist")

                    profile_photo = request.FILES.get('profile_photo')
                    if profile_photo:
                        profile_pic_path = os.path.join(settings.MEDIA_ROOT, 'profilepic', profile_photo.name)
                        with open(profile_pic_path, 'wb+') as destination:
                            for chunk in profile_photo.chunks():
                                destination.write(chunk)
                        profile_pic_full_path = os.path.join('D:\\wms2\\media\\profilepic', profile_photo.name)
                        with connection.cursor() as cursor:
                            cursor.execute(
                                """
                                INSERT INTO employee_images (employee_id, images)
                                VALUES (%s, %s)
                                """,
                                [emp_id, profile_pic_full_path]
                            )

                    attachments = request.FILES.getlist('attachments')
                    for attachment in attachments:
                        attachment_path = os.path.join(settings.MEDIA_ROOT, 'uploads', attachment.name)
                        with open(attachment_path, 'wb+') as destination:
                            for chunk in attachment.chunks():
                                destination.write(chunk)
                        attachment_full_path = os.path.join('D:\\wms2\\media\\uploads', attachment.name)
                        with connection.cursor() as cursor:
                            cursor.execute(
                                """
                                INSERT INTO employee_images (employee_id, images)
                                VALUES (%s, %s)
                                """,
                                [emp_id, attachment_full_path]
                            )

                    if removed_profile_pic:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                """
                                DELETE FROM employee_images WHERE employee_id = %s AND images LIKE %s
                                """,
                                [emp_id, '%profilepic%']
                            )

                    for attachment_id in removed_attachments:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                """
                                DELETE FROM employee_images WHERE id = %s
                                """,
                                [attachment_id]
                            )

                return JsonResponse({'success': 'Employee updated successfully'})
            except Exception as e:
                logger.error("Error updating employee: %s", str(e))
                return JsonResponse({'error': str(e)}, status=400)

        elif operation == 'delete':
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT modify_employee(%s, %s)
                        """,
                        [operation, emp_id]
                    )
                return JsonResponse({'success': 'Employee deleted successfully'})
            except Exception as e:
                logger.error("Error deleting employee: %s", str(e))
                return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def add_equipment(request):
    if request.method == 'POST':
        equipment_name = request.POST.get('equipment_name')
        subcategory_name = request.POST.get('subcategory_name')
        category_name = request.POST.get('category_name')
        type = request.POST.get('type')
        dimension_h = request.POST.get('dimension_h')
        dimension_w = request.POST.get('dimension_w')
        dimension_l = request.POST.get('dimension_l')
        weight = request.POST.get('weight')
        volume = request.POST.get('volume')
        hsn_no = request.POST.get('hsn_no')
        country_origin = request.POST.get('country_origin')
        attachment = request.FILES.get('attachment')
        status = request.POST.get('status')
        created_by = request.user.id
        created_date = datetime.now()

        # Save image to the desired location
        attachment_path = None
        if attachment:
            attachment_path = os.path.join(settings.MEDIA_ROOT, 'attachments', attachment.name)
            os.makedirs(os.path.dirname(attachment_path), exist_ok=True)  # Ensure the directory exists
            with open(attachment_path, 'wb') as f:
                for chunk in attachment.chunks():
                    f.write(chunk)

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT public.add_equipment_list(
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    );
                    """,
                    [
                        equipment_name,
                        subcategory_name,
                        category_name,
                        type,
                        dimension_h,
                        dimension_w,
                        dimension_l,
                        weight,
                        volume,
                        hsn_no,
                        country_origin,
                        attachment_path if attachment else None,
                        status,
                        created_by,
                        created_date
                    ]
                )
                return redirect(f'/equipment_list/?subcategory_id={subcategory_name}')
        except IntegrityError as e:
            error_message = str(e)
            if 'duplicate key value violates unique constraint "unique_equipment_name"' in error_message:
                error_message = 'Equipment name already exists. Please choose a different name.'
            print("An unexpected error occurred:", error_message)
            return render(request, 'product_tracking/index.html', {'error': error_message})
        except Exception as e:
            print("An unexpected error occurred:", e)
            return render(request, 'product_tracking/index.html', {'error': 'An unexpected error occurred'})
    else:
        username = None
        if request.user.is_authenticated:
            username = request.user.username
        # Fetch subcategories
        subcategories = []
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT id, category_name, name FROM get_sub()')
                subcategories = [{'id': row[0], 'category_name': row[1], 'name': row[2]} for row in cursor.fetchall()]
        except Exception as e:
            print("Error fetching subcategories:", e)
        return render(request, 'product_tracking/Equipment.html',
                      {'username': username, 'subcategories': subcategories})


@login_required
def insert_vendor(request):
    if request.method == 'POST':
        # Retrieve form data
        vendor_name = request.POST.get('vendor_name')
        purchase_date = request.POST.get('purchase_date')
        unit_price = request.POST.get('unit_price')
        rental_price = request.POST.get('rental_price')
        reference_no = request.POST.get('reference_no')
        attachment = request.FILES.get('attachment')
        unit = request.POST.get('unitValue')
        # Extract dynamically generated input box values
        serial_numbers = []
        barcode_numbers = []
        for i in range(1, int(unit) + 1):
            serial_number = request.POST.get(f'serialNumber{i}', '')
            barcode_number = request.POST.get(f'barcodeNumber{i}', '')
            serial_numbers.append(serial_number)
            barcode_numbers.append(barcode_number)

        equipment_id = request.POST.get('equipmentId')
        subcategory_id = None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT sub_category_id FROM equipment_list WHERE id = %s",
                    [equipment_id]
                )
                subcategory_id = cursor.fetchone()[0]
        except Exception as e:
            print(f"An unexpected error occurred while fetching equipment ID: {e}")

        attachment_path = None
        if attachment:
            attachment_path = os.path.join(settings.MEDIA_ROOT, 'attachments', attachment.name)
            os.makedirs(os.path.dirname(attachment_path), exist_ok=True)  # Ensure the directory exists
            with open(attachment_path, 'wb') as f:
                for chunk in attachment.chunks():
                    f.write(chunk)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT add_stock(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);",
                    [equipment_id, vendor_name, purchase_date, unit_price, rental_price, reference_no, attachment_path,
                     unit, serial_numbers, barcode_numbers]
                )
            print('Stock Details added successfully')
            return redirect(f'/equipment_list/?subcategory_id={subcategory_id}')
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return render(request, 'product_tracking/index.html', {'error': 'An unexpected error occurred'})
    else:
        # Handle GET request
        username = None
        if request.user.is_authenticated:
            username = request.user.username
        return render(request, 'product_tracking/performance.html', {'username': username})


@login_required
def subcategory_dropdown(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT id, category_name, name FROM get_sub()')
            subcategories = [{'id': row[0], 'category_name': row[1], 'name': row[2]} for row in cursor.fetchall()]
            print('sub category fetched successfully:', subcategories)
            return JsonResponse({'subcategories': subcategories}, safe=False)
    except Exception as e:
        # Handle exceptions, maybe log the error for debugging
        print("Error fetching sub category:", e)
        return JsonResponse({'subcategories': []})


@login_required
def get_category_name(request):
    try:
        subcategory_id = request.GET.get('subcategory_id')
        # Fetch category name based on subcategory_id
        with connection.cursor() as cursor:
            cursor.execute('SELECT category_name FROM get_sub() WHERE id = %s', [subcategory_id])
            row = cursor.fetchone()
            category_name = row[0] if row else None
        return JsonResponse({'category_name': category_name})
    except Exception as e:
        # Handle exceptions, maybe log the error for debugging
        print("Error fetching category name:", e)
        return JsonResponse({'category_name': None})


@login_required
def subcategory_list(request, category_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM get_sub(%s)", [category_id])
        rows = cursor.fetchall()

    subcategory_listing = []
    for row in rows:
        created_date = row[5].strftime('%d-%m-%Y')
        subcategory_listing.append({
            'id': row[0],
            'category_name': row[1],
            'name': row[2],
            'status': row[3],
            'created_by': row[4],
            'created_date': created_date
        })

    context = {
        'subcategories': json.dumps(subcategory_listing),  # Ensure JSON is correctly formatted
        'category_id': category_id
    }
    return render(request, 'product_tracking/sub-performance1.html', context)


@login_required
def equipment_list(request):
    subcategory_id = request.GET.get('subcategory_id')
    if not subcategory_id:
        return JsonResponse({'error': 'Missing subcategory_id parameter'}, status=400)

    equipment_listing = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM get_equipment_list(%s)", [subcategory_id])
            rows = cursor.fetchall()

            for row in rows:
                created_date = row[15].strftime('%d-%m-%Y')
                equipment_listing.append({
                    'id': row[0],
                    'equipment_name': row[1],
                    'sub_category_name': row[2],
                    'category_type': row[3],
                    'type': row[4],
                    'dimension_height': row[5],
                    'dimension_width': row[6],
                    'dimension_length': row[7],
                    'weight': row[8],
                    'volume': row[9],
                    'hsn_no': row[10],
                    'country_origin': row[11],
                    'attachment': row[12],
                    'status': row[13],
                    'created_by': row[14],
                    'created_date': created_date
                })
    except Exception as e:
        print("Error fetching equipment list:", e)
        return JsonResponse({'error': str(e)}, status=500)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'equipments': equipment_listing})

    context = {
        'equipment_listing': json.dumps(equipment_listing),
        'subcategory_id': subcategory_id
    }
    return render(request, 'product_tracking/Equipment.html', context)


@login_required
def delete_equipment_list(request, id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.callproc('delete_equipment', [id])
            return JsonResponse({'message': 'Equipment deleted successfully', 'Equipment_id:': id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to delete Equipment', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def update_equipment(request, id):
    if request.method == 'POST':
        print('Received POST request to update employee details')

        # Extract the form data
        name = request.POST.get('employeeName')
        sub_category_name = request.POST.get('subCategory')
        category_type = request.POST.get('categoryType')
        equipment_type = request.POST.get('equipmentType')
        dimension_height = request.POST.get('dimensionHeight')
        dimension_width = request.POST.get('dimensionWidth')
        dimension_length = request.POST.get('dimensionLength')
        weight = request.POST.get('weight')
        volume = request.POST.get('volume')
        hsn_no = request.POST.get('hsnNo')
        country = request.POST.get('employeeCountry')
        # status = request.POST.get('statusText')

        print(id, name, sub_category_name, country)
        try:
            print('Inside the try block')
            with connection.cursor() as cursor:
                print('Inside the cursor')
                cursor.callproc('update_equipment', [
                    id, name, sub_category_name, category_type, equipment_type, dimension_height,
                    dimension_width, dimension_length, weight, volume, hsn_no, country
                ])
                print('Inside the callproc', id)
                updated_employee_id = cursor.fetchone()[0]
                print(updated_employee_id)
            return JsonResponse({
                'message': 'Employee details updated successfully',
                'updated_employee_id': updated_employee_id
            })
        except Exception as e:
            return JsonResponse({'error': 'Failed to update employee details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


@login_required
def edit_subcategory_dropdown(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT id, category_name, name FROM get_sub()')
            sub = [{'id': row[0], 'category_name': row[1], 'name': row[2]} for row in cursor.fetchall()]
            print('sub category fetched successfully:', sub)
            return JsonResponse({'sub': sub}, safe=False)
    except Exception as e:
        # Handle exceptions, maybe log the error for debugging
        print("Error fetching sub category:", e)
        return JsonResponse({'sub': []})


@login_required
def edit_get_category_name(request):
    try:
        subcategory_id = request.GET.get('subcategory_id')
        # Fetch category name based on subcategory_id
        with connection.cursor() as cursor:
            cursor.execute('SELECT category_name FROM get_sub() WHERE id = %s', [subcategory_id])
            row = cursor.fetchone()
            category_name = row[0] if row else None
        return JsonResponse({'category_name': category_name})
    except Exception as e:
        # Handle exceptions, maybe log the error for debugging
        print("Error fetching category name:", e)
        return JsonResponse({'category_name': None})


def fetch_stock_status(request, equipment_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM get_stock_status(%s)", [equipment_id])
        stock_data = cursor.fetchone()
        print('Equipment ID:', equipment_id)
        print('Equipment ID:', equipment_id, stock_data)

    if stock_data is not None:
        unit_count = stock_data[0]
        stock_status = 'Stock in completed' if unit_count > 0 else 'Stock in pending'
    else:
        unit_count = 0
        stock_status = 'Stock in pending'
    return JsonResponse({'unit_count': unit_count, 'stock_status': stock_status})


def fetch_serial_barcode_no(request, equipment_id):
    # Execute the PostgreSQL function
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM get_serial_barcode_no(%s)", [equipment_id])
        rows = cursor.fetchall()
        if rows:
            # If multiple rows are returned, create a list of dictionaries
            data = [{'serial_number': row[0], 'barcode_number': row[1]} for row in rows]
        else:
            # If no rows are returned, return an error
            return JsonResponse({'error': 'No data found for equipment ID ' + str(equipment_id)}, status=404)

    return JsonResponse(data, safe=False)


def get_dimension_list(request, equipment_id):
    print('inside the function')
    # Execute the PostgreSQL function
    with connection.cursor() as cursor:
        print('inside the object of cursor')
        cursor.execute("SELECT * FROM get_dimension_list_stock(%s)", [equipment_id])
        rows = cursor.fetchall()  # Fetch all rows
        print('row values:', rows)
        if rows:
            # Initialize dictionaries to hold single and aggregated data
            dimension_details = {}
            stock_details = {
                'vender_name': '',
                'purchase_date': '',
                'unit_price': '',
                'rental_price': '',
                'reference_no': '',
                'unit': '',
                'serial_no': [],
                'barcode_no': []
            }

            # Extract common dimension details from the first row
            first_row = rows[0]
            dimension_details = {
                'dimension_height': first_row[0] or '',
                'dimension_width': first_row[1] or '',
                'dimension_length': first_row[2] or '',
                'weight': first_row[3] or '',
                'volume': first_row[4] or '',
                'hsn_no': first_row[5] or '',
                'country_origin': first_row[6] or '',
                'status': first_row[7] or '',
                'created_by': first_row[8] or '',
                'created_date': first_row[9].strftime('%d-%m-%Y') if first_row[9] else ''
            }

            # Check if any row has serial numbers or barcode numbers
            has_stock_details = any(row[16] or row[17] for row in rows)

            if has_stock_details:
                # Aggregate serial numbers and barcode numbers
                for row in rows:
                    stock_details['serial_no'].append(row[16] or '')
                    stock_details['barcode_no'].append(row[17] or '')

                # Assign single values to stock_details
                stock_details['vender_name'] = first_row[10] or ''
                stock_details['purchase_date'] = first_row[11].strftime('%d-%m-%Y') if first_row[11] else ''
                stock_details['unit_price'] = first_row[12] or ''
                stock_details['rental_price'] = first_row[13] or ''
                stock_details['reference_no'] = first_row[14] or ''
                stock_details['unit'] = first_row[15] or ''

            # Merge dictionaries
            data = {**dimension_details, **stock_details}
            print('Values are shown in the table are:', data)
        else:
            # If no rows are returned, return an error
            return JsonResponse({'error': 'No data found for equipment ID ' + str(equipment_id)}, status=404)

    return JsonResponse(data)


@login_required()
def Stock_list(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/stocks.html', {'username': username})


@login_required
def fetch_equipment_list(request):
    if request.method == 'POST':
        category_id = request.POST.get('category_type', '')
        start = int(request.POST.get('start', 0))
        limit = int(request.POST.get('limit', 10))

        print(f"Fetching data for category: {category_id}, start: {start}, limit: {limit}")

        # Fetch paginated data
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM public.get_list(%s) OFFSET %s LIMIT %s
            """, [category_id, start, limit])
            rows = cursor.fetchall()
            print(f"Fetched rows: {rows}")

        # Fetch total count
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT el.equipment_name, el.sub_category_id, el.category_type
                    FROM public.equipment_list el
                    LEFT JOIN public.sub_category sc ON el.sub_category_id = sc.id
                    LEFT JOIN public.stock_details sd ON el.id = sd.equipment_id
                    WHERE sc.category_id = %s
                ) AS distinct_items
            """, [category_id])
            total_items = cursor.fetchone()[0]
            print(f"Total items: {total_items}")

        equipment_list = []
        for row in rows:
            equipment_list.append({
                'equipment_name': row[0],
                'sub_category_name': row[1],  # Ensure this is the correct index for sub_category_name
                'category_type': row[2],
                'unit_price': row[3],
                'rental_price': row[4],
                'total_units': row[5],
            })

        print(f"Equipment list: {equipment_list}")

        return JsonResponse({'totalItems': total_items, 'data': equipment_list}, safe=False)
    else:
        return JsonResponse({'error': 'Invalid request'})


@login_required
def stock_in(request, equipment_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.fetch_stock_details(%s)", [equipment_id])
            rows = cursor.fetchall()

        if rows:
            data = [{'id': row[0], 'serial_number': row[1], 'barcode_number': row[2], 'vendor_name': row[3],
                     'unit_price': row[4],
                     'rental_price': row[5], 'purchase_date': row[6], 'reference_no': row[7]} for row in rows]
        else:
            return JsonResponse({'error': 'No data found for equipment ID ' + str(equipment_id)}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    # Return the data as a JSON response
    return JsonResponse(data, safe=False)


@login_required
def update_stock_in(request, row_id):
    if request.method == 'POST':
        try:
            vender_name = request.POST.get('vender_name')
            serial_number = request.POST.get('serial_number')
            barcode_number = request.POST.get('barcode_number')
            unit_price = request.POST.get('unit_price')
            rental_price = request.POST.get('rental_price')
            purchase_date = request.POST.get('purchase_date')
            reference_no = request.POST.get('reference_no')

            with connection.cursor() as cursor:
                cursor.callproc('update_stock_in_function', [
                    row_id,
                    vender_name,
                    serial_number,
                    barcode_number,
                    unit_price,
                    rental_price,
                    purchase_date,
                    reference_no
                ])
            return JsonResponse({'success': True, 'message': 'Updated successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e), 'message': 'Not Updated successfully'})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
def fetch_stock_details_by_name(request):
    equipment_name = request.GET.get('equipment_name', '')

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM public.fetch_stock_details_by_name(%s)
            """,
            [equipment_name]
        )
        results = cursor.fetchall()

    # Format the results into a JSON response
    response_data = []
    for row in results:
        data = {
            'serial_number': row[0],
            'barcode_number': row[1],
            'vendor_name': row[2],
            'unit_price': row[3],
            'rental_price': row[4],
            'purchase_date': row[5],
            'reference_no': row[6],
        }
        response_data.append(data)

    return JsonResponse(response_data, safe=False)


@csrf_exempt
def add_event_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        event_id = request.POST.get('event_id')
        venue = request.POST.get('venue')
        client_name = request.POST.get('client_name')
        person_name = request.POST.get('person_name')
        created_by = request.session.get('user_id')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        # Ensure event_id is an integer if provided
        event_id = int(event_id) if event_id else None

        # Set created_date for CREATE and UPDATE actions
        created_date = datetime.now() if action in ['CREATE', 'UPDATE'] else None

        # Validation for CREATE and UPDATE actions
        if action == 'CREATE':
            if not (venue and client_name and person_name and start_date and end_date):
                return JsonResponse({'success': False, 'error_message': 'All fields must be filled out'}, status=400)
        elif action == 'UPDATE':
            if not event_id:
                return JsonResponse({'success': False, 'error_message': 'Event ID is required for update'}, status=400)
            if not (venue and client_name and person_name and start_date and end_date):
                return JsonResponse({'success': False, 'error_message': 'All fields must be filled out'}, status=400)
        elif action == 'DELETE':
            if not event_id:
                return JsonResponse({'success': False, 'error_message': 'Event ID is required for deletion'},
                                    status=400)
        else:
            return JsonResponse({'success': False, 'error_message': 'Invalid action'}, status=400)

        with connection.cursor() as cursor:
            cursor.callproc('public.manage_event', [
                action,
                event_id,
                venue,
                client_name,
                person_name,
                created_by,
                created_date,
                start_date,
                end_date
            ])
            result = cursor.fetchall()

        # Process the result to convert it to JSON serializable format
        columns = [col[0] for col in cursor.description]
        result = [dict(zip(columns, row)) for row in result]

        return JsonResponse({'success': True, 'data': result})

    return JsonResponse({'success': False, 'error_message': 'Invalid request method or action'}, status=400)


def get_eventvalue(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.calender")
            events = cursor.fetchall()
            events_list = []
            for event in events:
                start_date = event[6].strftime('%Y-%m-%d') if event[6] else None
                end_date = (event[7] + timedelta(days=1)).strftime('%Y-%m-%d') if event[7] else start_date
                events_list.append({
                    'id': event[0],
                    'title': f"{event[1]} - {event[2]} - {event[3]}",
                    'start': start_date,
                    'end': end_date,
                    'extendedProps': {
                        'venue': event[1],
                        'client_name': event[2],
                        'person_name': event[3]
                    }
                })
            return JsonResponse(events_list, safe=False)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        return JsonResponse({'success': False, 'error_message': 'There was an error retrieving events.'}, status=500)


@login_required
def add_job(request):
    print('inside the add job function')
    if request.method == 'POST':
        print('inside the add job post method')
        title = request.POST.get('title')
        client_name = request.POST.get('client_name')
        venue_address = request.POST.get('venue_address')
        status = request.POST.get('status')
        crew_types = request.POST.getlist('crew_type')
        crew_type = ','.join(crew_types)
        no_of_container = request.POST.get('no_of_container')
        employee = request.POST.getlist('prep_sheet')
        employee = ','.join(employee)
        setup_date = request.POST.get('setup_date')
        rehearsal_date = request.POST.get('rehearsal_date')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        category_ids = request.POST.getlist('category_name')
        equipment_ids = request.POST.getlist('equipment_name')
        quantities = request.POST.getlist('quantity')
        number_of_days = request.POST.getlist('number_of_days')
        amounts = request.POST.getlist('amount')

        category_ids = [int(id) for id in category_ids]
        equipment_ids = [int(id) for id in equipment_ids]

        print('Fetched data:', title, client_name, venue_address, status, crew_type, no_of_container, employee,
              setup_date, rehearsal_date, start_date, end_date, category_ids, equipment_ids, quantities, number_of_days,
              amounts)

        try:
            with connection.cursor() as cursor:
                cursor.callproc(
                    'jobs_master_list',
                    ('CREATE', None, None, title, client_name, venue_address, status, crew_type, no_of_container,
                     employee, setup_date, rehearsal_date,
                     start_date, end_date, category_ids, equipment_ids, quantities, number_of_days, amounts)
                )
                data = cursor.fetchall()
                print('Returned data:', data)
                return redirect('add_job')
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return render(request, 'product_tracking/index.html', {'error': 'An unexpected error occurred'})

    username = None
    if request.user.is_authenticated:
        username = request.user.username

    return render(request, 'product_tracking/jobs.html', {'username': username})


@login_required
def fetch_venue_addresses(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT venue_address FROM public.connects WHERE type = 'Venue'")
        venue_addresses = [row[0] for row in cursor.fetchall()]

    return JsonResponse({'venue_addresses': venue_addresses})


@login_required
def fetch_client_name(request):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT name, company_name FROM public.connects"
        )
        client_names = {
            'Names': [],
            'CompanyNames': []
        }
        for row in cursor.fetchall():
            name, company_name = row
            if name:
                client_names['Names'].append(name)
            if company_name:
                client_names['CompanyNames'].append(company_name)

    return JsonResponse({'client_names': client_names})


@login_required
def get_new_row_data(request):
    with connection.cursor() as cursor:
        # Execute the PostgreSQL function to fetch the equipment name
        cursor.execute("SELECT equipment_name FROM equipment_list")
        equipment_name = cursor.fetchone()[0]  # Fetch the first row and the first column value

    # Create a dictionary containing the equipment details
    data = {
        'equipment_name': equipment_name,
        'quantity': 1,  # Example quantity, replace with actual data
        'startdate': '2024-01-02',  # Example start date, replace with actual data
        'enddate': '2025-01-04'  # Example end date, replace with actual data
    }

    return JsonResponse(data)


@login_required
def fetch_master_categories(request):
    if request.method == 'GET':
        with connection.cursor() as cursor:
            cursor.execute("SELECT category_id, category_name FROM master_category")
            master_categories = cursor.fetchall()
            master_categories_list = [{'category_id': row[0], 'category_name': row[1]} for row in master_categories]
            print(master_categories_list)
        return JsonResponse({'master_categories': master_categories_list})


@login_required
def fetch_equipment_names(request):
    if request.method == 'GET':
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, equipment_name FROM equipment_list")
            equipment_names = cursor.fetchall()
            print('fetch equipment Names with id:', id)
            equipment_names_list = [{'id': row[0], 'equipment_name': row[1]} for row in equipment_names]
            print('fetch equipment Names with id:', id, equipment_names_list)

        return JsonResponse({'equipment_names': equipment_names_list})


@login_required
def fetch_rental_price(request):
    equipment_id = request.GET.get('equipment_id')
    if equipment_id:
        with connection.cursor() as cursor:
            cursor.execute("SELECT rental_price FROM stock_details WHERE equipment_id = %s", [equipment_id])
            row = cursor.fetchone()
            if row:
                rental_price = row[0]
                return JsonResponse({'rental_price': rental_price})
            else:
                return JsonResponse({'error': 'Stock details not found'}, status=404)
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def insert_data(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        client_name = request.POST.get('client_name')
        venue_address = request.POST.get('venue_address')
        status = request.POST.get('status')
        crew_type = request.POST.get('crew_type')
        no_of_container = request.POST.get('no_of_container')
        employee = request.POST.get('employee')
        setup_date = request.POST.get('setup_date')
        rehearsal_date = request.POST.get('rehearsal_date')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        category_name = request.POST.get('category_name')
        equipment_name = request.POST.get('equipment_name')
        quantity = request.POST.get('quantity')
        number_of_days = request.POST.get('number_of_days')
        amount = request.POST.get('amount')

        print('Received employee:', employee)

        employee_list = employee.split(',') if employee else []

        print('Processed employee_list:', employee_list)

        with connection.cursor() as cursor:
            cursor.execute("SELECT insert_row_data(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                           [None, title, client_name, venue_address, status, crew_type, no_of_container, employee,
                            setup_date, rehearsal_date, start_date,
                            end_date, category_name, equipment_name, quantity, number_of_days, amount])

            print('insert data success:', employee)

        return JsonResponse({'message': 'Data inserted successfully'}, status=201)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def get_employee_name(request):
    if request.method == 'GET':
        with connection.cursor() as cursor:
            cursor.execute("SELECT DISTINCT id, name FROM employee")
            employee_names = cursor.fetchall()
            print('Fetch employee names:', employee_names)
            employee_names_list = [{'id': row[0], 'name': row[1]} for row in employee_names]
            print('Fetch employee Names with id:', employee_names_list)
        return JsonResponse({'employee_names': employee_names_list})


@login_required
def delete_row_from_temp_table(request):
    print('inside the delete row table')
    if request.method == 'POST':
        print('inside the post method')
        category_name = request.POST.get('category')
        equipment_name = request.POST.get('equipment')
        quantity = request.POST.get('quantity')
        number_of_days = request.POST.get('days')
        amount = request.POST.get('amount')

        print('fetch the data:', category_name, equipment_name, quantity, number_of_days, amount)

        try:
            print('inside the try block')
            with connection.cursor() as cursor:
                print('inside the cursor and cursor in row')
                cursor.execute(
                    "DELETE FROM temp WHERE quantity = %s AND number_of_days = %s AND amount = %s",
                    [quantity, number_of_days, amount]
                )
                print('Delete the row:', category_name, equipment_name, quantity, number_of_days, amount)
            return JsonResponse({'message': 'Row deleted successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)


@login_required
def jobs_list(request):
    print('Received Jobs List')
    jobs_listing = []
    processed_job_reference_nos = set()
    try:
        print('inside the get job list')
        with connection.cursor() as cursor:
            print('inside the cursor connection object')
            # cursor.execute("select * from public.jobs")
            cursor.callproc('jobs_master_list',
                            ['READ', None, None, None, None, None, None, None, None, None, None, None, None, None, None,
                             None, None, None, None])
            jobs = cursor.fetchall()
            print('Fetch the jobs:', jobs)

            columns = [col[0] for col in cursor.description]
            for job in jobs:
                job_dict = dict(zip(columns, job))
                job_reference_no = job_dict.get('job_reference_no')
                if job_reference_no not in processed_job_reference_nos:
                    jobs_listing.append(job_dict)
                    processed_job_reference_nos.add(job_reference_no)

    except Exception as e:
        print("Error fetching Jobs list:", e)
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse(jobs_listing, safe=False)


@login_required
def get_status_counts(request):
    with connection.cursor() as cursor:
        # cursor.execute("SELECT COUNT(*) FROM public.jobs WHERE status = 'Perfoma';")
        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT job_reference_no, status FROM public.jobs WHERE status = 'Perfoma' GROUP BY  job_reference_no, status) AS unique_perfoma;")
        perfoma_count = cursor.fetchone()[0]
        print('Perfoma status count:', perfoma_count)

        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT job_reference_no, status FROM public.jobs WHERE status = 'Prepsheet' GROUP BY job_reference_no, status) AS unique_prepsheets;")
        prepsheet_count = cursor.fetchone()[0]
        print('Prepsheet Status count:', prepsheet_count)

        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT job_reference_no, status FROM public.jobs WHERE status = 'Quotation' GROUP BY job_reference_no, status) AS unique_quats;")
        quatation_count = cursor.fetchone()[0]
        print('Quatation Status count:', quatation_count)

        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT job_reference_no, status FROM public.jobs WHERE status = 'Delivery Challan' GROUP BY job_reference_no, status) AS unique_deliveries;")
        deliveryChallan_count = cursor.fetchone()[0]
        print('Delivery Challan Status count:', deliveryChallan_count)

    data = {
        'perfoma_count': perfoma_count,
        'prepsheet_count': prepsheet_count,
        'quatation_count': quatation_count,
        'deliveryChallan_count': deliveryChallan_count,
    }

    return JsonResponse(data)


@login_required
def update_jobs(request, id):
    if request.method == 'POST':
        print('Received POST request to update Jobs details')
        job_reference_no = request.POST.get('jobReferenceNo')
        title = request.POST.get('title')
        status = request.POST.get('status')
        print(id, job_reference_no, title, status)
        try:
            print('inside the try block')
            with connection.cursor() as cursor:
                print('inside the cursor')
                cursor.callproc('jobs_master_list',
                                ['UPDATE', id, job_reference_no, title, None, None, status, None, None, None, None,
                                 None, None, None, None, None, None, None, None])
                print('inside the callproc', id, status)
                updated_jobs_id = cursor.fetchone()
                print(updated_jobs_id)
            return JsonResponse(
                {'message': 'Jobs details updated successfully', 'updated_jobs_id': updated_jobs_id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to update jobs details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


@login_required
def delete_jobs(request, id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.callproc('jobs_master_list',
                            ['DELETE', id, None, None, None, None, None, None, None, None, None, None, None, None, None,
                             None, None, None, None])

        return JsonResponse({'message': 'Job deleted successfully'}, status=200)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)


@login_required
def add_connects(request):
    if request.method == 'POST':
        c_type = request.POST.get('type')
        created_by = int(request.user.id)
        created_date = datetime.now()
        c_status = request.POST.get('status')

        if c_type == 'Company':
            c_company_name = request.POST.get('company_name')
            c_gst_no = request.POST.get('gst_no')
            c_pan_no = request.POST.get('pan_no')
            c_contact_person_name = request.POST.get('person_name')
            c_contact_person_no = request.POST.get('person_no')
            c_contact_email = request.POST.get('contact_email')
            c_billing_address = request.POST.get('billing_address')
            c_office_address = request.POST.get('office_address')
            c_social_no = request.POST.get('social_no')
            c_city = request.POST.get('city')
            c_country = request.POST.get('country')
            c_post_code = request.POST.get('post_code')
            c_company, c_name, c_email, c_mobile, c_address, c_venue_name, c_venue_address, c_client_name, c_client_address, c_client_mobile_no = (
                None, None, None, None, None, None, None, None, None, None)
        elif c_type == 'Individual':
            c_name = request.POST.get('name')
            c_email = request.POST.get('email')
            c_mobile = request.POST.get('mobile_no')
            c_address = request.POST.get('address')
            c_city = request.POST.get('city')
            c_country = request.POST.get('country')
            c_post_code = request.POST.get('post_code')
            c_social_no = request.POST.get('social_no')
            c_company = request.POST.get('company')
            (c_company_name, c_gst_no, c_pan_no, c_contact_person_name, c_contact_person_no, c_contact_email,
             c_billing_address, c_office_address, c_venue_name,
             c_venue_address, c_client_name, c_client_address,
             c_client_mobile_no) = None, None, None, None, None, None, None, None, None, None, None, None, None
        elif c_type == 'Venue':
            c_venue_name = request.POST.get('venue_name')
            c_venue_address = request.POST.get('venue_address')
            c_city = request.POST.get('city')
            c_country = request.POST.get('country')
            c_post_code = request.POST.get('post_code')
            (c_company_name, c_name, c_email, c_mobile, c_address, c_social_no, c_company, c_gst_no, c_pan_no,
             c_contact_person_name, c_contact_person_no, c_contact_email,
             c_billing_address,
             c_office_address, c_client_name, c_client_address,
             c_client_mobile_no) = None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None
        else:
            c_client_name = request.POST.get('client_name')
            c_client_address = request.POST.get('client_address')
            c_client_mobile_no = request.POST.get('client_mobile_no')
            c_city = request.POST.get('city')
            c_country = request.POST.get('country')
            c_post_code = request.POST.get('post_code')
            (c_company_name, c_name, c_email, c_mobile, c_address, c_social_no, c_company, c_gst_no, c_pan_no,
             c_contact_person_name, c_contact_person_no, c_contact_email,
             c_billing_address,
             c_office_address, c_venue_name,
             c_venue_address) = None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None

        try:
            with connection.cursor() as cursor:
                cursor.callproc('connect_master', ['CREATE', None, c_type, c_name, c_email, c_mobile, c_address, c_city,
                                                   c_country, c_post_code, created_by, created_date, c_status,
                                                   c_company_name, c_gst_no, c_pan_no, c_contact_person_name,
                                                   c_contact_person_no, c_contact_email, c_billing_address,
                                                   c_office_address, c_social_no, c_company, c_venue_name,
                                                   c_venue_address, c_client_name, c_client_address,
                                                   c_client_mobile_no])

                columns = [col[0] for col in cursor.description]
                result_set = [dict(zip(columns, row)) for row in cursor.fetchall()]

                # Check the result set and retrieve the result_message
                result_message = result_set[0].get('result_message', None) if result_set else None

                if result_message == 'Connects added successfully.':
                    return redirect('add_connects')
                else:
                    error_message = 'Error occurred while adding connects.'
                    return render(request, 'product_tracking/contacts.html', {'error_message': error_message})
        except IntegrityError:
            error_message = 'Error occurred while adding connects.'
            return render(request, 'product_tracking/contacts.html', {'error_message': error_message})
    else:
        username = None
        if request.user.is_authenticated:
            username = request.user.username
    # If the request method is GET, render the form
    return render(request, 'product_tracking/contacts.html', {'username': username})


@login_required
def company_dropdown_view(request):
    if request.method == 'GET':
        # Call the stored procedure to fetch the connect records
        with connection.cursor() as cursor:
            cursor.callproc('connect_master', [
                'READ',  # operation
                None,  # in_id
                None,  # in_type
                None,  # in_name
                None,  # in_email
                None,  # in_mobile
                None,  # in_address
                None,  # in_city
                None,  # in_country
                None,  # in_post_code
                None,  # in_created_by
                None,  # in_created_date
                None,  # in_status
                None,  # in_company_name
                None,  # in_gst
                None,  # in_pan
                None,  # in_contact_person_name
                None,  # in_contact_person_no
                None,  # in_contact_email
                None,  # in_billing_address
                None,  # in_office_address
                None,  # in_social_no
                None  # in_company

            ])
            result = cursor.fetchall()
            columns = [col[0] for col in cursor.description]

        # Convert the result to a list of dictionaries
        data = [dict(zip(columns, row)) for row in result]

        # Return the result as JSON
        return JsonResponse(data, safe=False)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)


@login_required()
def connect_list(request):
    with connection.cursor() as cursor:
        cursor.callproc("connect_master",
                        ["READ", None, None, None, None, None, None, None, None, None, None, None, None,
                         None, None, None, None, None, None, None, None, None, None, None, None, None, None, None])

        connects_list = cursor.fetchall()

    # Convert the result into a list of dictionaries
    item_listing = []
    for item in connects_list:
        # Adjust the indexing based on the actual columns returned
        created_date_time = item[10].strftime('%d-%m-%Y')
        item_data = {
            'id': item[0],
            'type': item[1] if len(item) > 1 and item[1] else None,
            'city': item[6] if len(item) > 6 and item[6] else None,
            'country': item[7] if len(item) > 7 and item[7] else None,
            'post_code': item[8] if len(item) > 8 and item[8] else None,
            'created_by': item[9] if len(item) > 9 and item[9] else None,
            'created_date_time': created_date_time,
            'status': item[11] if len(item) > 11 and item[11] else None,
        }
        # Add type-specific fields based on the type
        if item_data['type'] == 'Individual':
            item_data.update({
                'name': item[2],
                'email': item[3],
                'mobile': item[4],
                'address': item[5],
            })
        elif item_data['type'] == 'Company':
            item_data.update({
                'company_name': item[12],
                'gst_no': item[13],
                'pan_no': item[14],
                'contact_person_name': item[15],
                'contact_person_no': item[16],
                'contact_email': item[17],
                'billing_address': item[18],
                'office_address': item[19],
                'social_no': item[20],
            })
        elif item_data['type'] == 'Venue':
            item_data.update({
                'venue_name': item[22],  # Adjust based on your database structure
                'venue_address': item[23],  # Adjust based on your database structure
            })
        elif item_data['type'] == 'Client':
            item_data.update({
                'client_name': item[24],  # Adjust based on your database structure
                'client_address': item[25],  # Adjust based on your database structure
                'client_mobile_no': item[26],
            })
        item_listing.append(item_data)

    return JsonResponse(item_listing, safe=False)


@login_required()
def update_connect(request, id):
    print('inside the update function')
    if request.method == 'POST':
        print('inside the POST method')
        data = json.loads(request.body)
        type = data.get('type')
        name = data.get('name')
        email = data.get('email')
        mobile = data.get('mobile')
        address = data.get('address')
        city = data.get('city')
        country = data.get('country')
        post_code = data.get('post_code')

        print(id, type, name, email, mobile, address)

        try:
            print('inside the try block')
            with connection.cursor() as cursor:
                print('inside the cursor')
                cursor.callproc('connect_master',
                                ['UPDATE', id, type, name, email, mobile, address, city, country, post_code, None, None,
                                 None, None, None,
                                 None, None, None, None, None, None, None, None, None, None, None, None, None])
                print('call the callproc object')
                updated_id = cursor.fetchone()
                print('Updated ID:', updated_id)
            return JsonResponse(
                {'message': 'Contact details updated successfully', 'updated_id': updated_id})
        except Exception as e:
            print('Exception:', str(e))
            return JsonResponse({'error': 'Failed to update contact details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


@login_required()
def delete_connect(request, id):
    if request.method == 'POST':
        # Call the stored procedure to delete the connect record
        with connection.cursor() as cursor:
            cursor.callproc('connect_master',
                            ['DELETE', id, None, None, None, None, None, None, None, None, None, None, None, None, None,
                             None, None, None, None, None, None, None, None, None, None, None, None, None])
        # Return a success response
        return JsonResponse({'message': 'Contact deleted successfully'}, status=200)
    else:
        # Return an error response for invalid request method
        return JsonResponse({'error': 'Invalid request method'}, status=400)
