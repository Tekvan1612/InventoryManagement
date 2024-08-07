import json
import traceback
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.db import connection, transaction
from django.contrib.auth.models import User
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest,HttpResponseServerError
import os
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from psycopg2 import IntegrityError
from django.shortcuts import get_object_or_404
from django.core.files.storage import default_storage
import cloudinary
from cloudinary.uploader import upload
from django.utils import timezone


logger = logging.getLogger(__name__)


#Create your views here.
def index(request):
    # Retrieve session data
    username = request.session.get('username', 'N/A')
    user_id = request.session.get('user_id', None)  # Retrieve the user_id to check if it's correctly stored
    modules = request.session.get('modules', None)

    # Log the retrieved session data
    print(f"Accessing index view")
    print(f"Session Data - Username: {username}, User ID: {user_id}, Modules:{modules}")

    if not username or username == 'N/A':
        print("No username in session; redirecting to login")
        return redirect('login_view')

    # If session data is valid, render the index page with the session data
    return render(request, 'product_tracking/index.html', {
        'username': username,
        'user_id': user_id  # Optionally pass user_id to the template if needed
    })



def custom_login(request):
    try:
        if request.method == 'POST':
            username = request.POST.get('username')
            password = request.POST.get('password')

            with connection.cursor() as cursor:
                cursor.execute("SELECT user_exists, user_id FROM public.validate_user(%s, %s, %s)", [username, password, True])
                result = cursor.fetchone()

                if result and result[0]:
                    user_id = result[1]
                    cursor.execute(
                        "SELECT mm.module_name FROM user_junction_module ujm JOIN module_master mm ON ujm.module_id = mm.module_id WHERE ujm.user_id = %s",
                        [user_id])
                    modules = cursor.fetchall()

                    request.session['username'] = username
                    request.session['user_id'] = user_id
                    request.session['modules'] = [module[0] for module in modules]

                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'status': 'success', 'redirect_url': redirect('index').url})
                    else:
                        return redirect('index')
                else:
                    messages.error(request, "Invalid login details")
                    return render(request, 'product_tracking/page-login.html')

        return render(request, 'product_tracking/page-login.html')
    except Exception as e:
        logger.error(f"Error in custom_login view: {e}", exc_info=True)
        return render(request, 'product_tracking/error.html', {'error': str(e)})

def logout_view(request):
    try:
        logout(request)
        return redirect('login_view')
    except Exception as e:
        logger.error(f"Error in logout_view: {e}", exc_info=True)
        return render(request, 'product_tracking/error.html', {'error': str(e)})


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
    username = request.session.get('username')
    return render(request, 'product_tracking/app-calender.html', {'username': username})


def contact(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/contacts.html', {'username': username})


def employee(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/employee.html', {'username': username})


def performance(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/performance.html', {'username': username})


def task(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/jobs.html', {'username': username})


# Category Module
def add_category(request):
    username = request.session.get('username')
    if request.method == 'POST':
        category_name = request.POST.get('category_name').upper()
        description = request.POST.get('description')
        status = request.POST.get('status') == '1'
        created_by = request.session.get('user_id')
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
        return render(request, 'product_tracking/performance1.html', {'username': username})


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


@csrf_exempt
def update_category(request, category_id):
    if request.method == 'POST':
        print('Received POST request to update category details')

        # Extract the form data
        category_name = request.POST.get('categoryName').upper()
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


def get_category_dropdown(request, category_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT category_id, category_name FROM master_category WHERE category_id = %s", [category_id])
        category_data = cursor.fetchone()
        category_id = category_data[0]
        category_name = category_data[1]

    return JsonResponse({'category_id': category_id, 'category_name': category_name})


# Sub Category Module
def add_sub_category(request):
    if request.method == 'POST':
        category_id = request.POST.get('category_id')
        subcategory_name = request.POST.get('subcategory_name').upper()
        subcategory_types = request.POST.getlist('subcategory_type[]')  # Get the list of subcategory types
        status = request.POST.get('status')
        created_by = request.session.get('user_id')
        created_date = datetime.now()

        types_combined = ','.join([stype.upper() for stype in subcategory_types])  # Combine and convert to upper case

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT add_sub_category(%s, %s, %s, %s, %s, %s);",
                    [category_id, subcategory_name, types_combined, status, created_by, created_date]
                )
            return JsonResponse({'success': True})
        except Exception as e:
            print("An unexpected error occurred:", e)  # Print the error message
            return JsonResponse({'success': False, 'message': 'An unexpected error occurred: ' + str(e)})
    else:
        categories = subcategory_list(request)
        return render(request, 'product_tracking/sub-performance1.html',
                      {'categories': categories})

def subcategory_list(request, category_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM get_sub(%s)", [category_id])
        rows = cursor.fetchall()

    subcategory_listing = []
    for row in rows:
        created_date = row[6].strftime('%d-%m-%Y')
        subcategory_listing.append({
            'id': row[0],
            'category_name': row[1],
            'name': row[2],
            'type': row[3],
            'status': row[4],
            'created_by': row[5],
            'created_date': created_date
        })

    context = {
        'subcategories': json.dumps(subcategory_listing),
        'category_id': category_id
    }
    return render(request, 'product_tracking/sub-performance1.html', context)


def update_subcategory(request, id):
    if request.method == 'POST':
        print('Received POST request to update sub category details')

        # Extract the form data
        name = request.POST.get('categoryName')
        subcategory_types = request.POST.get('subcategoryTypes')

        print('Received data:', {
            'id': id,
            'name': name,
            'subcategoryTypes': subcategory_types
        })

        try:
            with connection.cursor() as cursor:
                cursor.callproc('update_subcategory', [id, name, subcategory_types])
                updated_category_id = cursor.fetchone()[0]
                print(updated_category_id)
            return JsonResponse(
                {'message': 'Sub Category details updated successfully', 'updated_category_id': updated_category_id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to update sub category details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})

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


def fetch_events(request):
    # Extract month and year from query parameters
    month = request.GET.get('month')
    year = request.GET.get('year')

    # Default to current month and year if not provided
    if not month or not year:
        from datetime import datetime
        now = datetime.now()
        month = now.month
        year = now.year

    # Convert month and year to integers
    try:
        month = int(month)
        year = int(year)
    except ValueError:
        return JsonResponse({'error': 'Invalid month or year'}, status=400)

    # SQL query to fetch events based on month and year
    query = """
        SELECT event_id, venue, client_name, person_name, start_date, end_date, created_date
        FROM public.calender
        WHERE EXTRACT(MONTH FROM start_date) = %s AND EXTRACT(YEAR FROM start_date) = %s
    """

    with connection.cursor() as cursor:
        cursor.execute(query, [month, year])
        rows = cursor.fetchall()

        # Convert the rows to a list of dictionaries
        events_list = []
        for row in rows:
            created_date_time = row[6]
            if created_date_time:
                # Format the datetime to get the time part in 12-hour format with AM/PM
                created_date_time = created_date_time.strftime('%I:%M %p')  # %I = 12-hour clock, %p = AM/PM
            else:
                created_date_time = 'No time available'

            events_list.append({
                'event_id': row[0],
                'venue': row[1],
                'client_name': row[2],
                'person_name': row[3],
                'start_date': row[4].strftime('%Y-%m-%d'),
                'end_date': row[5].strftime('%Y-%m-%d') if row[5] else '',
                'created_date': created_date_time
            })

    return JsonResponse(events_list, safe=False)

# User Management Module
def add_user(request):
    username = request.session.get('username')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        status = request.POST.get('status') == '1'
        modules = request.POST.getlist('modules')
        created_by = int(request.session.get('user_id'))
        created_date = datetime.now()
        print('Add the USER:', username, password, status, modules, created_by, created_date)

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
        return render(request, 'product_tracking/user.html', {'username': username, 'employee_names': employee_names})


def user_list(request):
    print('Received data:')
    user_listing = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM getuser()")
            rows = cursor.fetchall()
            print("fetched user list:", rows)

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


# Employees Module
def add_employee(request):
    username = request.session.get('username')
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
        created_by = request.session.get('user_id')
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

    return render(request, 'product_tracking/employee.html', {'employees': get_all_employees(), 'username': username})


def get_all_employees():
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM employee")
        employees = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
    return employees


def employee_dropdown(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM employee")
        employees = cursor.fetchall()
        employee_list = [{'id': emp[0], 'name': emp[1]} for emp in employees]

    return JsonResponse({'employees': employee_list})


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
                    try:
                        image_relative_path = os.path.relpath(image_path, settings.MEDIA_ROOT)
                        image_url = os.path.join(settings.MEDIA_URL, image_relative_path).replace('\\', '/')
                    except ValueError as ve:
                        logger.error("ValueError occurred while computing relative path: %s", str(ve))
                        image_url = os.path.join(settings.MEDIA_URL, 'profilepic/default.jpg')
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
def modify_employee(request):
    print('Fetch the ID:', id)
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


# Equipment Module

@csrf_exempt
def add_equipment(request):
    if request.method == 'POST':
        if not request.session.get('username'):
            return JsonResponse({'success': False, 'message': 'Session expired. Please log in again.'}, status=401)

        try:
            equipment_name = request.POST.get('equipment_name')
            subcategory_id = request.POST.get('subcategory_id')
            category_type = request.POST.get('category_type')
            type = request.POST.get('type')
            dimension_h = request.POST.get('dimension_h')
            dimension_w = request.POST.get('dimension_w')
            dimension_l = request.POST.get('dimension_l')
            volume = request.POST.get('volume')
            weight = request.POST.get('weight')
            hsn_no = request.POST.get('hsn_no')
            country_origin = request.POST.get('country_origin')
            status = request.POST.get('status') == 'true'
            created_by = request.session.get('user_id')
            created_date = datetime.now()

            logger.info("Received POST data: %s", request.POST)

            if not category_type:
                return JsonResponse({'success': False, 'message': 'Category type is required'})

            attachment = request.FILES.get('attachment')
            if attachment:
                try:
                    logger.info("Uploading image to Cloudinary")
                    result = upload(attachment)
                    attachment_url = result['secure_url']
                    logger.info("Image uploaded successfully: %s", attachment_url)
                except Exception as e:
                    logger.error("Cloudinary error: %s", str(e))
                    return JsonResponse({'success': False, 'message': 'Cloudinary upload error: ' + str(e)})
            else:
                attachment_url = ''
                logger.info("No attachment uploaded")

            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT add_equipment_list(
                            %s::character varying, 
                            %s::integer, 
                            %s::character varying, 
                            %s::character varying, 
                            %s::character varying, 
                            %s::character varying, 
                            %s::character varying, 
                            %s::character varying, 
                            %s::character varying, 
                            %s::integer, 
                            %s::character varying, 
                            %s::character varying, 
                            %s::boolean, 
                            %s::integer, 
                            %s::timestamp without time zone)
                    """, [equipment_name, subcategory_id, category_type, type, dimension_h, dimension_w, dimension_l,
                          weight, volume, hsn_no, country_origin, attachment_url, status, created_by, created_date])
                logger.info("Equipment data inserted into database successfully")
            except Exception as db_error:
                logger.error("Database error: %s", str(db_error))
                return JsonResponse({'success': False, 'message': 'Database error: ' + str(db_error)})

            return JsonResponse({'success': True, 'message': 'Equipment added successfully'})

        except ValueError as ve:
            logger.error("ValueError in add_equipment view: %s", str(ve))
            return JsonResponse({'success': False, 'message': 'Invalid input data: ' + str(ve)})
        except Exception as e:
            logger.error("Error in add_equipment view: %s", str(e))
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})

def insert_vendor(request):
    if request.method == 'POST':
        # Retrieve form data
        vendor_name = request.POST.get('vendor_name')
        purchase_date = request.POST.get('purchase_date')
        unit_price = request.POST.get('unit_price')
        rental_price = request.POST.get('rental_price')
        reference_no = request.POST.get('reference_no')
        unit = request.POST.get('unitValue')
        attachment = request.FILES.get('attachment')

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

        # Handle file upload
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
                    "SELECT add_stock(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL);",
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


def subcategory_list(request, category_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM get_subcategory(%s)", [category_id])
        rows = cursor.fetchall()

    subcategory_listing = []
    for row in rows:
        created_date = row[6].strftime('%d-%m-%Y')
        subcategory_listing.append({
            'id': row[0],
            'category_name': row[1],
            'name': row[2],
            'type': row[3],
            'status': row[4],
            'created_by': row[5],
            'created_date': created_date
        })

    context = {
        'subcategories': json.dumps(subcategory_listing),
        'category_id': category_id
    }
    return render(request, 'product_tracking/sub-performance1.html', context)


def equipment_list(request):
    username = request.session.get('username')
    subcategory_id = request.GET.get('subcategory_id')

    if not subcategory_id:
        return JsonResponse({'error': 'Missing subcategory_id parameter'}, status=400)

    try:
        subcategory_id = int(subcategory_id)
    except ValueError:
        return JsonResponse({'error': 'Invalid subcategory_id parameter'}, status=400)

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
                    'attachment': row[12],  # Ensure this is the Cloudinary URL
                    'status': row[13],
                    'created_by': row[14],
                    'created_date': created_date
                })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'equipments': equipment_listing})

    context = {
        'equipment_listing': json.dumps(equipment_listing),
        'subcategory_id': subcategory_id,
        'username': username
    }
    return render(request, 'product_tracking/Equipment.html', context)


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


def update_equipment(request, id):
    if request.method == 'POST':
        print('Received POST request to update employee details')

        # Extract the form data
        name = request.POST.get('employeeName').upper()
        sub_category_name = request.POST.get('subCategory').upper()
        category_type = request.POST.get('categoryType').upper()
        equipment_type = request.POST.get('equipmentType').upper()
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


def stock_list(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/stocks.html', {'username': username})


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


def stock_in(request, equipment_id):
    print('inside the stock in')
    try:
        print('Execute this try block')
        with connection.cursor() as cursor:
            print('Execute the cursor object')
            cursor.execute("SELECT * FROM public.fetch_stock_details(%s)", [equipment_id])
            rows = cursor.fetchall()
            print('Fetch the stock_details:', rows)

        if rows:
            print('inside the rows')
            data = [{'id': row[0], 'serial_number': row[1], 'barcode_number': row[2], 'vendor_name': row[3],
                     'unit_price': row[4],
                     'rental_price': row[5], 'purchase_date': row[6], 'reference_no': row[7]} for row in rows]
            print('insert the correct data:', data)
        else:
            return JsonResponse({'error': 'No data found for equipment ID ' + str(equipment_id)}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    # Return the data as a JSON response
    return JsonResponse(data, safe=False)


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


def add_job(request):
    username = request.session.get('username')
    print('inside the add job function')
    if request.method == 'POST':
        print('inside the add job post method')
        title = request.POST.get('title')
        client_name = request.POST.get('client_name')
        contact_person_name = request.POST.get('contact_person_name')
        contact_person_number = request.POST.get('contact_person_number')
        venue_address = request.POST.get('venue_address')
        status = request.POST.get('status')
        crew_types = request.POST.getlist('crew_type')
        crew_type = ','.join(crew_types)
        no_of_container = request.POST.get('no_of_container')
        employees = request.POST.getlist('prep_sheet')
        employee = ','.join(employees)
        setup_date = request.POST.get('setup_date')
        rehearsal_date = request.POST.get('rehearsal_date')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        total_days = request.POST.get('total_days')
        amount_row = request.POST.get('amount_row')
        discount = request.POST.get('discount')
        discounted_amount = request.POST.get('discounted_amount')
        total_amount = request.POST.get('total_amount')

        print('fetch the amount after discount:', discounted_amount)

        # Fetching multiple values as lists
        category_name = request.POST.getlist('category_name')
        equipment_ids = request.POST.getlist('equipment_name')
        quantities = request.POST.getlist('quantity')
        number_of_days = request.POST.getlist('number_of_days')
        amounts = request.POST.getlist('amount')
        print('Fetch the category NAME:', category_name)

        # Convert strings to integers for category_ids and equipment_ids
        equipment_ids = [int(id) for id in equipment_ids]

        # Assuming you have the user ID stored in the session for the created_by field
        created_by = request.session.get('user_id')
        created_date = datetime.now()

        print('Fetch the data:', title, client_name, contact_person_name, contact_person_number, venue_address, status,
              crew_type, no_of_container, employee,
              setup_date, rehearsal_date, start_date,
              end_date, total_days, amount_row, discount, discounted_amount, total_amount, category_name, equipment_ids,
              quantities, number_of_days, amounts, created_by, created_date)

        try:
            with connection.cursor() as cursor:
                # Print the query for debugging purposes
                query = f"SELECT * FROM jobs_master_list('CREATE', NULL, NULL, '{title}', '{client_name}', '{venue_address}', '{status}', '{crew_type}', '{no_of_container}', '{employee}', '{setup_date}'::date, '{rehearsal_date}'::date, '{start_date}'::date, '{end_date}'::date, '{discounted_amount}', ARRAY{category_name}::integer[], ARRAY{equipment_ids}::integer[], ARRAY{quantities}::varchar[], ARRAY{number_of_days}::varchar[], ARRAY{amounts}::varchar[], {created_by}, '{created_date}');"
                print("Executing query:", query)

                cursor.callproc(
                    'jobs_master_list',
                    (
                        'CREATE', None, None, title, client_name, contact_person_name, contact_person_number,
                        venue_address,
                        status, crew_type, no_of_container,
                        employee, setup_date, rehearsal_date, start_date, end_date, total_days, amount_row, discount,
                        discounted_amount, total_amount, category_name, equipment_ids,
                        quantities, number_of_days, amounts, created_by, created_date)
                )
                # Fetch the returned data from the cursor
                data = cursor.fetchall()
                print('Returned data:', data)
                return JsonResponse({'success': True})
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return JsonResponse({'success': False}, status=400)
    return render(request, 'product_tracking/jobs.html', {'username': username})


def fetch_venue_addresses(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT venue_address FROM public.connects WHERE type = 'Venue'")
        venue_addresses = [row[0] for row in cursor.fetchall()]

    return JsonResponse({'venue_addresses': venue_addresses})


def fetch_client_name(request):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT type, name, company_name FROM public.connects"
        )
        client_names = []
        for row in cursor.fetchall():
            client_type, name, company_name = row
            if name:
                client_names.append({'type': client_type, 'name': name})
            if company_name:
                client_names.append({'type': client_type, 'name': company_name})

    return JsonResponse({'client_names': client_names})


def save_new_row(request):
    if request.method == 'POST':
        job_reference_no = request.POST.get('jobReferenceNo')
        title = request.POST.get('title')
        client_name = request.POST.get('client_name')
        venue_address = request.POST.get('venue_address')
        status = request.POST.get('status')
        crew_type = request.POST.get('crew_type')
        no_of_container = request.POST.get('no_of_container')
        employee = request.POST.get('prep_sheet')
        setup_date = request.POST.get('setup_date')
        rehearsal_date = request.POST.get('rehearsal_date')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        category_name = request.POST.get('category_name')
        equipment_id = request.POST.get('equipment_name')
        quantity = request.POST.get('quantity')
        number_of_days = request.POST.get('number_of_days')
        amount = request.POST.get('amount')

        print('Received details:', job_reference_no, title, client_name, venue_address, status, crew_type,
              no_of_container, employee, setup_date, rehearsal_date, start_date, end_date, category_name,
              equipment_id, quantity, number_of_days, amount)

        if not (job_reference_no and title and client_name and venue_address and status and setup_date and
                rehearsal_date and start_date and end_date and category_name and equipment_id and quantity and
                number_of_days and amount):
            return JsonResponse({'success': False, 'error': 'Missing required fields'})

        try:
            print('Inside the try block of save new row')
            with connection.cursor() as cursor:
                print('Inside the cursor')

                # Fetch equipment_name from equipment_list table using equipment_id
                cursor.execute("""
                    SELECT equipment_name FROM equipment_list WHERE id = %s;
                """, [equipment_id])
                equipment_name_row = cursor.fetchone()
                if not equipment_name_row:
                    return JsonResponse({'success': False, 'error': 'Equipment ID not found'})
                equipment_name = equipment_name_row[0]

                print('Fetched equipment_name:', equipment_name)

                cursor.execute("""
                    INSERT INTO public.jobs (job_reference_no, title, client_name, venue_address, status, crew_type,
                                             no_of_container, employee, setup_date, rehearsal_date, show_start_date,
                                             show_end_date, category_name, equipment_name, quantity, number_of_days,
                                             amount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """,
                               [job_reference_no, title, client_name, venue_address, status, crew_type, no_of_container,
                                employee, setup_date, rehearsal_date, start_date, end_date, category_name,
                                equipment_name, quantity, number_of_days, amount])
                print('Cursor executed successfully', category_name, equipment_name)
                new_job_id = cursor.fetchone()[0]
                print('New job ID:', new_job_id)
            return JsonResponse({'success': True, 'new_job_id': new_job_id})
        except Exception as e:
            print('Exception occurred:', str(e))
            traceback.print_exc()
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


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


def fetch_master_categories(request):
    if request.method == 'GET':
        with connection.cursor() as cursor:
            cursor.execute("SELECT category_id, category_name FROM master_category ORDER BY category_name")
            master_categories = cursor.fetchall()
            master_categories_list = [{'category_id': row[0], 'category_name': row[1]} for row in master_categories]
            print(master_categories_list)
        return JsonResponse({'master_categories': master_categories_list})


def fetch_equipment_names(request):
    if request.method == 'GET':
        category_name = request.GET.get('category_name')
        if category_name:
            with connection.cursor() as cursor:

                # Select distinct equipment names from equipment_list with corresponding stock in stock_details
                cursor.execute("""
                    SELECT DISTINCT ON (e.equipment_name) e.id, e.equipment_name
                    FROM equipment_list e
                    JOIN stock_details s ON e.id = s.equipment_id
                    WHERE e.category_type = %s AND s.unit > 0
                    ORDER BY e.equipment_name, s.id DESC
                    """, [category_name])
                equipment_names = cursor.fetchall()
                equipment_names_list = [{'id': row[0], 'equipment_name': row[1]} for row in equipment_names]
                return JsonResponse({'equipment_names': equipment_names_list})
        else:
            return JsonResponse({'error': 'Category name is required.'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method.'}, status=405)


@csrf_exempt
def check_equipment_in_temp(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        equipment_id = request.POST.get('equipment_name')  # assuming equipment_name is the equipment ID

        logger.info(f"Received title: {title}, equipment_id: {equipment_id}")

        if equipment_id and title:
            # Fetch the equipment name based on the equipment ID
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT equipment_name
                    FROM equipment_list
                    WHERE id = %s
                """, [equipment_id])
                equipment_name_result = cursor.fetchone()

                if equipment_name_result:
                    equipment_name = equipment_name_result[0]

                    # Check if the equipment name and title exist in the temp table
                    cursor.execute("""
                        SELECT 1
                        FROM temp
                        WHERE equipment_name = %s
                          AND title = %s
                    """, [equipment_name, title])
                    exists = cursor.fetchone()

                    if exists:
                        return JsonResponse({'exists': True, 'equipment_name': equipment_name})
                    else:
                        return JsonResponse({'exists': False, 'equipment_name': equipment_name})
                else:
                    return JsonResponse({'error': 'Invalid equipment ID.'}, status=400)
        else:
            return JsonResponse({'error': 'Both equipment ID and job reference number are required.'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method.'}, status=405)


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


def insert_data(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        client_name = request.POST.get('client_name')
        contact_person_name = request.POST.get('contact_person_name')
        contact_person_number = request.POST.get('contact_person_number')
        venue_address = request.POST.get('venue_address')
        status = request.POST.get('status')
        crew_type = request.POST.get('crew_type')
        no_of_container = request.POST.get('no_of_container')
        employee = request.POST.get('employee')
        setup_date = request.POST.get('setup_date')
        rehearsal_date = request.POST.get('rehearsal_date')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        total_days = request.POST.get('total_days')
        amount_row = request.POST.get('amount_row')
        discount = request.POST.get('discount')
        discount_amount = request.POST.get('discount_amount')
        total_amount = request.POST.get('total_amount')
        category_name = request.POST.get('category_name')
        equipment_name = request.POST.get('equipment_name')
        quantity = request.POST.get('quantity')
        number_of_days = request.POST.get('number_of_days')
        amount = request.POST.get('amount')

        print('Received employee:', employee)

        employee_list = employee.split(',') if employee else []

        print('Processed employee_list:', employee_list)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT insert_row_data(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [None, title, client_name, contact_person_name, contact_person_number, venue_address, status, crew_type,
                 no_of_container, employee,
                 setup_date, rehearsal_date, start_date,
                 end_date, total_days, amount_row, discount, discount_amount, total_amount, category_name,
                 equipment_name, quantity, number_of_days, amount])

            print('insert data success:', employee)

        return JsonResponse({'message': 'Data inserted successfully'}, status=201)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def get_employee_name(request):
    if request.method == 'GET':
        with connection.cursor() as cursor:
            cursor.execute("SELECT DISTINCT id, name FROM employee")
            employee_names = cursor.fetchall()
            print('Fetch employee names:', employee_names)
            employee_names_list = [{'id': row[0], 'name': row[1]} for row in employee_names]
            print('Fetch employee Names with id:', employee_names_list)
        return JsonResponse({'employee_names': employee_names_list})


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


def jobs_list(request):
    print('Received Jobs List')
    jobs_listing = []
    processed_job_reference_nos = set()
    try:
        print('inside the get job list')
        with connection.cursor() as cursor:
            print('inside the cursor connection object')
            cursor.callproc('jobs_master_list',
                            ['READ', None, None, None, None, None, None, None, None, None, None, None, None, None, None,
                             None, None, None, None, None, None, None, None, None, None, None, None, None])
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


@csrf_exempt
def update_job_details(request, id):
    print('Inside the Job Details with ID:', id)
    if request.method == 'POST':
        print('Fetch the POST method')
        try:
            print('Inside the try block')
            data = json.loads(request.body)
            category_name = data.get('category_name')
            equipment_name = data.get('equipment_name')
            quantity = data.get('quantity')
            number_of_days = data.get('number_of_days')
            amount = data.get('amount')
            print('Fetch the DATA:', data, category_name, equipment_name, quantity, number_of_days, amount)

            with connection.cursor() as cursor:
                print('inside the cursor block')
                cursor.execute("""
                    UPDATE job_details
                    SET category_name = %s,
                        equipment_name = %s,
                        quantity = %s,
                        number_of_days = %s,
                        amount = %s
                    WHERE id = %s
                """, [category_name, equipment_name, quantity, number_of_days, amount, id])
                print('Updated the DATA:', id, category_name, equipment_name, quantity, number_of_days, amount)

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request method'})


def job_details_page(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/job_details.html', {'username': username})


def get_job_details(request):
    job_id = request.GET.get('jobId')

    if job_id:
        try:
            with connection.cursor() as cursor:
                # Fetch job details from jobs table
                cursor.execute("""
                    SELECT j.id, j.title, j.client_name, j.contact_person_name,
                      j.contact_person_number, j.venue_address, j.status,
                        j.crew_type, j.no_of_container, j.employee,
                        j.setup_date, j.rehearsal_date, j.show_start_date, j.show_end_date,
                        j.total_days, j.amount_row, j.discount, j.amount_after_discount, j.total_amount
                    FROM public.jobs j
                    WHERE j.id = %s
                """, [job_id])
                job_row = cursor.fetchone()
                print('Fetch the job Row:', job_row)

                if job_row:
                    job_data = {
                        'id': job_row[0],
                        'title': job_row[1],
                        'client_name': job_row[2],
                        'contact_person_name': job_row[3],
                        'contact_person_number': job_row[4],
                        'venue_address': job_row[5],
                        'status': job_row[6],
                        'crew_type': job_row[7],
                        'no_of_container': job_row[8],
                        'employee': job_row[9],
                        'setup_date': job_row[10].strftime('%Y-%m-%d') if job_row[10] else None,
                        'rehearsal_date': job_row[11].strftime('%Y-%m-%d') if job_row[11] else None,
                        'show_start_date': job_row[12].strftime('%Y-%m-%d') if job_row[12] else None,
                        'show_end_date': job_row[13].strftime('%Y-%m-%d') if job_row[13] else None,
                        'total_days': job_row[14],
                        'amount_row': job_row[15],
                        'discount': job_row[16],
                        'amount_after_discount': job_row[17],
                        'total_amount': job_row[18],
                    }
                    print('Fetch the Data:', job_data)
                    # Fetch job_details related to the job_id
                    cursor.execute("""
                        SELECT d.id, d.category_name, d.equipment_name, d.quantity, d.number_of_days, d.amount
                        FROM public.job_details d
                        WHERE d.job_id = %s
                    """, [job_id])
                    job_details_rows = cursor.fetchall()

                    job_details_data = []
                    for row in job_details_rows:
                        job_detail_data = {
                            'id': row[0],  # Include id field
                            'category_name': row[1],
                            'equipment_name': row[2],
                            'quantity': row[3],
                            'number_of_days': row[4],
                            'amount': row[5]
                        }
                        print('Fetch the DATA:', job_detail_data)
                        job_details_data.append(job_detail_data)

                    return JsonResponse({'success': True, 'job_data': job_data, 'job_details': job_details_data})
                else:
                    return JsonResponse({'success': False, 'error': 'Job details not found'}, status=404)

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'success': False, 'error': 'Invalid request'})


def delete_job_row(request, job_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM public.jobs WHERE id = %s;", [job_id])
                return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})


def delete_jobs(request, id):
    print('Inside the delete jobs', id)
    if request.method == 'POST':
        print('Check the POST method')
        with connection.cursor() as cursor:
            print('Inside the cursor connection object')
            cursor.callproc('jobs_master_list',
                            [
                                'DELETE',  # operation
                                id,  # in_id
                                None,  # in_job_reference_no
                                None,  # in_title
                                None,  # in_client_name
                                None,  # in_contact_person_name
                                None,  # in_contact_person_number
                                None,  # in_venue_address
                                None,  # in_status
                                None,  # in_crew_type
                                None,  # in_no_of_container
                                None,  # in_employee
                                None,  # in_setup_date
                                None,  # in_rehearsal_date
                                None,  # in_show_start_date
                                None,  # in_show_end_date
                                None,  # in_total_days
                                None,  # in_amount_row
                                None,  # in_discount
                                None,  # in_amount_after_discount
                                None,  # in_total_amount
                                [],  # in_category_id
                                [],  # in_equipment_id
                                [],  # in_quantity
                                [],  # in_number_of_days
                                [],  # in_amount
                                None,  # in_created_by
                                None  # in_created_date
                            ])
            print('Check the data')
        return JsonResponse({'message': 'Job deleted successfully'}, status=200)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)


def add_connects(request):
    if request.method == 'POST':
        c_type = request.POST.get('type')
        created_by = int(request.session.get('user_id'))
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

            print('Fetch the details of company:', c_contact_person_no)
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


def warehouse_master(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/warehouse-master.html', {'username': username})


def add_warehouse_master(request):
    if request.method == 'POST':
        company_name = request.POST.get('warehouseCompanyName')
        phone_no = request.POST.get('warehousePhoneNo')
        address = request.POST.get('warehouseName')

        with connection.cursor() as cursor:
            cursor.callproc('warehouse_master', ['CREATE', None, company_name, phone_no, address])
            warehouse = cursor.fetchall()
            print('Fetch warehouse:', warehouse)
            return redirect('warehouse_master')

    return render(request, 'product_tracking/warehouse-master.html', )


def warehouse_master_list(request):
    warehouse_master_listing = []
    try:
        with connection.cursor() as cursor:
            cursor.callproc('warehouse_master',
                            ['READ', None, None, None, None])
            rows = cursor.fetchall()

            for row in rows:
                warehouse_master_listing.append({
                    'id': row[0],
                    'company_name': row[1],
                    'phone_no': row[2],
                    'address': row[3],
                })
    except Exception as e:
        print("Error fetching Warehouse Master List:", e)
    return JsonResponse(warehouse_master_listing, safe=False)


def update_warehouse(request, id):
    if request.method == 'POST':
        print('Received POST request to update Jobs details')
        company_name = request.POST.get('jobReferenceNo')
        phone_no = request.POST.get('title')
        address_name = request.POST.get('valuesShow')
        print(id, company_name, phone_no, address_name)
        try:
            print('inside the try block')
            with connection.cursor() as cursor:
                print('inside the cursor')
                cursor.callproc('warehouse_master',
                                ['UPDATE', id, company_name, phone_no, address_name])
                print('inside the callproc', id, address_name)
                updated_jobs_id = cursor.fetchone()
                print(updated_jobs_id)
            return JsonResponse(
                {'message': 'Jobs details updated successfully', 'updated_jobs_id': updated_jobs_id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to update jobs details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


def delete_warehouse_master(request, id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.callproc('warehouse_master', ['DELETE', id, None, None, None])
        return JsonResponse({'message': 'Job deleted successfully'}, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=400)


def company_name_dropdown(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM public.company_master")
        companies = cursor.fetchall()

    company_list = [{'id': row[0], 'name': row[1]} for row in companies]
    return JsonResponse(company_list, safe=False)


def company_master(request):
    if request.method == 'POST':
        name = request.POST.get('companyName')
        gst_no = request.POST.get('companyGstNo')
        email = request.POST.get('companyEmail')
        company_logo = request.FILES.get('companyLogo')
        address = request.POST.get('companyAddress')

        company_logo_attachment = None
        if company_logo:
            company_logo_attachment = 'C:/Users/admin/PycharmProjects/Project/wms2/media/uploads/{}'.format(
                company_logo.name)
            with open(company_logo_attachment, 'wb') as f:
                for chunk in company_logo.chunks():
                    f.write(chunk)

        try:
            with connection.cursor() as cursor:
                cursor.callproc('company_master',
                                ['CREATE', None, name, gst_no, email, company_logo_attachment, address])
                company = cursor.fetchall()
                print('Inserted values are:', company)
                return redirect('warehouse_master')
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return render(request, 'product_tracking/index.html', {'error': 'An unexpected error occurred'})

    # If the request method is GET, render the form
    return render(request, 'product_tracking/warehouse-master.html', )


def company_master_list(request):
    company_master_listing = []
    try:
        with connection.cursor() as cursor:
            cursor.callproc('company_master',
                            ['READ', None, None, None, None, None, None])
            rows = cursor.fetchall()

            for row in rows:
                company_master_listing.append({
                    'id': row[0],
                    'name': row[1],
                    'gst_no': row[2],
                    'email': row[3],
                    'company_logo': row[4],
                    'address': row[5],
                })
    except Exception as e:
        print("Error fetching Company Master List:", e)
    return JsonResponse(company_master_listing, safe=False)


def update_company(request, id):
    if request.method == 'POST':
        name = request.POST.get('companyName')
        CompanyGstNo = request.POST.get('jobMail')
        companyEmailId = request.POST.get('companyEmailId')  # Ensure this matches the form input name
        company_address = request.POST.get('companyAddress')

        # if not CompanyGstNo:
        #     return JsonResponse({'error': 'GST No cannot be empty'})
        try:
            with connection.cursor() as cursor:
                cursor.callproc('company_master',
                                ['UPDATE', id, name, CompanyGstNo, companyEmailId, None, company_address])
                updated_company_id = cursor.fetchone()
            return JsonResponse(
                {'message': 'Company details updated successfully', 'updated_company_id': updated_company_id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to update company details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


def delete_company_master(request, id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.callproc('company_master', ['DELETE', id, None, None, None, None, None])
        return JsonResponse({'message': 'Company list deleted successfully'}, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=400)


def fetch_subcategory_name(request, subcategory_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, name FROM public.sub_category
                WHERE id = %s
            """, [subcategory_id])
            row = cursor.fetchone()
            print('Fetch the sub category ID:', row)

        if row:
            subcategory_id, subcategory_name = row
            return JsonResponse({'subcategory_id': subcategory_id, 'subcategory_name': subcategory_name})
        else:
            return JsonResponse({'error': 'Subcategory not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def fetch_subcategory_type(request, subcategory_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT type FROM public.sub_category
                WHERE id = %s
            """, [subcategory_id])
            row = cursor.fetchone()
            print('Fetch the subcategory type ID:', row)

        if row:
            subcategory_type = row[0]  # Extract the type from the tuple
            if isinstance(subcategory_type, str):  # Ensure it's a string
                return JsonResponse({'subcategory_type': subcategory_type})
            else:
                return JsonResponse({'error': 'Invalid type format'}, status=500)
        else:
            return JsonResponse({'error': 'Subcategory not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_category_type(request):
    if request.method == 'GET' and 'subcategory_id' in request.GET:
        subcategory_id = request.GET.get('subcategory_id')
        print('fetch the subcategory id of equipment name:', subcategory_id)

        # Fetch category_id from sub_category based on subcategory_id
        subcategory_query = """
            SELECT category_id FROM sub_category
            WHERE id = %s
        """
        with connection.cursor() as cursor:
            cursor.execute(subcategory_query, [subcategory_id])
            subcategory_row = cursor.fetchone()
            print('Fetch the sub category id:', subcategory_row)

            if subcategory_row:
                category_id = subcategory_row[0]
                print('Fetch the category ID:', category_id)

                # Fetch category_name from master_category based on category_id
                master_category_query = """
                    SELECT category_name FROM master_category
                    WHERE category_id = %s
                """
                cursor.execute(master_category_query, [category_id])
                master_category_row = cursor.fetchone()
                print('Fetch the master category row:', master_category_row)

                if master_category_row:
                    category_name = master_category_row[0]
                    print('Fetch the category name Details:', category_name)
                    return JsonResponse({'category_name': category_name})
                else:
                    return JsonResponse({'error': 'Category name not found for the category ID.'}, status=404)
            else:
                return JsonResponse({'error': 'Subcategory ID not found.'}, status=404)
    else:
        return JsonResponse({'error': 'Invalid request method or parameters.'}, status=400)


def fetch_stock_details(request):
    print('Fetch the category ID:')
    try:
        category_id = request.GET.get('category_id')
        print('Fetch the category ID:', category_id)

        # Step 1: Retrieve subcategory IDs based on category_id
        subcategory_ids = []
        if category_id:
            subcategory_query = """
                SELECT id 
                FROM sub_category 
                WHERE category_id = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(subcategory_query, [category_id])
                subcategory_ids = [row[0] for row in cursor.fetchall()]

        # Step 2: Retrieve equipment IDs based on the retrieved subcategory IDs
        equipment_ids = []
        if subcategory_ids:
            equipment_query = """
                SELECT id 
                FROM equipment_list 
                WHERE sub_category_id IN %s
            """
            with connection.cursor() as cursor:
                cursor.execute(equipment_query, [tuple(subcategory_ids)])
                equipment_ids = [row[0] for row in cursor.fetchall()]

        # Step 3: Fetch stock details based on the retrieved equipment IDs
        stock_details_query = """
            SELECT sd.id, el.equipment_name, sd.vender_name, sd.purchase_date, sd.unit_price,
                   sd.rental_price, sd.reference_no, sd.attchment, sd.unit, sd.serial_no, sd.barcode_no,
                   el.sub_category_id, sc.name as sub_category_name, el.category_type, el.type, 
                   el.dimension_height, el.dimension_width, el.dimension_length, el.weight, el.volume,
                   el.hsn_no, el.country_origin, el.status
            FROM stock_details sd
            INNER JOIN equipment_list el ON sd.equipment_id = el.id
            INNER JOIN sub_category sc ON el.sub_category_id = sc.id
            WHERE sd.equipment_id IN %s
        """

        with connection.cursor() as cursor:
            if equipment_ids:
                cursor.execute(stock_details_query, [tuple(equipment_ids)])
            else:
                cursor.execute(stock_details_query, [[]])  # Ensure empty list to avoid SQL error

            rows = cursor.fetchall()
            stock_details = []
            for row in rows:
                stock_details.append({
                    'id': row[0],
                    'equipment_name': row[1],
                    'vender_name': row[2],
                    'purchase_date': row[3].strftime('%Y-%m-%d') if row[3] else None,
                    'unit_price': float(row[4]) if row[4] else 0.0,
                    'rental_price': float(row[5]) if row[5] else 0.0,
                    'reference_no': row[6],
                    'attchment': row[7],
                    'unit': row[8],
                    'serial_no': row[9],
                    'barcode_no': row[10],
                    'sub_category_id': row[11],
                    'sub_category_name': row[12],
                    'category_type': row[13],
                    'type': row[14],
                    'dimension_height': row[15],
                    'dimension_width': row[16],
                    'dimension_length': row[17],
                    'weight': row[18],
                    'volume': row[19],
                    'hsn_no': row[20],
                    'country_origin': row[21],
                    'status': row[22],
                })
            return JsonResponse(stock_details, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def fetch_client_contact_number(request):
    print('Inside the fetch client contact number')
    client_name = request.GET.get('client_name')
    client_type = request.GET.get('client_type')
    print('Fetch the client Name:', client_name)
    print('Fetch the client Type:', client_type)

    with connection.cursor() as cursor:
        print('Check the connection cursor')
        if client_type == 'Company':
            cursor.execute("""
                SELECT contact_person_name, contact_person_no
                FROM connects
                WHERE company_name = %s AND type = %s
            """, [client_name, client_type])
        else:
            # Handle other cases if needed
            return JsonResponse({'contact_person_name': '', 'contact_person_no': ''})

        print('Check the cursor object is executed')
        result = cursor.fetchone()
        print('Fetch the contact number successfully', result)

    contact_person_name = result[0] if result else ''
    contact_person_no = result[1] if result else ''  # Add this line
    return JsonResponse(
        {'contact_person_name': contact_person_name, 'contact_person_no': contact_person_no})  # Update this line


def print_jobs(request):
    job_id = request.GET.get('jobId')

    # Fetch job details from jobs table
    job_query = '''
        SELECT id, job_reference_no, title, client_name, contact_person_name, contact_person_number,
               venue_address, status, crew_type, no_of_container, employee, setup_date,
               rehearsal_date, show_start_date, show_end_date, total_days, amount_row, discount,
               amount_after_discount, total_amount, created_by, created_date
        FROM jobs
        WHERE id = %s
    '''

    # Fetch company details directly
    company_query = '''
        SELECT name as company_name, gst_no as company_gst_no, email as company_email,
               company_logo as company_logo_path, address as company_address
        FROM company_master
        LIMIT 1
    '''

    # Fetch job details from job_details table
    job_details_query = '''
        SELECT jd.id, 
               jd.job_id, 
               jd.category_name, 
               jd.equipment_name, 
               jd.quantity, 
               jd.number_of_days, 
               jd.amount,
               el.type
        FROM job_details jd
        JOIN equipment_list el
        ON jd.equipment_name = el.equipment_name
        WHERE jd.job_id = %s
    '''

    with connection.cursor() as cursor:
        cursor.execute(job_query, [job_id])
        job = cursor.fetchone()

        cursor.execute(company_query)
        company = cursor.fetchone()

        cursor.execute(job_details_query, [job_id])
        job_details = cursor.fetchall()

    # Prepare the response data
    job_data = {
        'id': job[0],
        'job_reference_no': job[1],
        'title': job[2],
        'client_name': job[3],
        'contact_person_name': job[4],
        'contact_person_number': job[5],
        'venue_address': job[6],
        'status': job[7],
        'crew_type': job[8],
        'no_of_container': job[9],
        'employee': job[10],
        'setup_date': job[11].strftime('%d-%m-%Y') if job[11] else None,
        'rehearsal_date': job[12].strftime('%d-%m-%Y') if job[12] else None,
        'show_start_date': job[13].strftime('%d-%m-%Y') if job[13] else None,
        'show_end_date': job[14].strftime('%d-%m-%Y') if job[14] else None,
        'total_days': job[15],
        'amount_row': job[16],
        'discount': job[17],
        'amount_after_discount': job[18],
        'total_amount': job[19],
        'created_by': job[20],
        'created_date': job[21].strftime('%Y-%m-%d %H:%M:%S') if job[21] else None,
        'company_name': company[0],
        'company_gst_no': company[1],
        'company_email': company[2],
        'company_logo_path': default_storage.url(company[3]) if company[3] else None,
        'company_address': company[4]
    }

    job_details_data = [
        {
            'id': detail[0],
            'job_id': detail[1],
            'category_name': detail[2],
            'equipment_name': detail[3],
            'quantity': detail[4],
            'number_of_days': detail[5],
            'amount': detail[6],
            'type': detail[7]  # Include category_type in the response data
        }
        for detail in job_details
    ]

    response_data = {
        'job': job_data,
        'job_details': job_details_data
    }

    return JsonResponse(response_data)


@csrf_exempt
def check_stock_availability(request):
    if request.method == 'POST':
        equipment_id = request.POST.get('equipment_id')
        requested_quantity = int(request.POST.get('quantity'))

        print('Fetching the details:', equipment_id, requested_quantity)

        with connection.cursor() as cursor:
            # Count the number of barcodes where scan_flag is FALSE or NULL
            cursor.execute("""
                SELECT COALESCE(COUNT(barcode_no), 0)
                FROM public.stock_details
                WHERE equipment_id = %s AND (scan_flag IS NULL OR scan_flag = TRUE)
            """, [equipment_id])
            available_barcode_units = cursor.fetchone()[0]
            print('Available barcode units with scan_flag TRUE or NULL:', available_barcode_units)

            # Check if the requested quantity is available
            if requested_quantity > available_barcode_units:
                return JsonResponse({
                    'status': 'error',
                    'message': f'The requested quantity is not available. The total available stock is: {available_barcode_units}'
                })
            else:
                return JsonResponse({
                    'status': 'success',
                    'available_units': available_barcode_units
                })

    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method.'
    })


@csrf_exempt
def update_all_job_details(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            formData = data.get('formData', {})
            rows = data.get('rows', [])
            jobId = data.get('jobId')

            print('Fetch the form DATA:', formData, rows)

            with connection.cursor() as cursor:
                # Update the jobs table
                cursor.execute("""
                    UPDATE jobs
                    SET title = %s,
                        client_name = %s,
                        contact_person_name = %s,
                        contact_person_number = %s,
                        venue_address = %s,
                        status = %s,
                        crew_type = %s,
                        no_of_container = %s,
                        employee = %s,
                        setup_date = %s,
                        rehearsal_date = %s,
                        show_start_date = %s,
                        show_end_date = %s,
                        total_days = %s,
                        amount_row = %s,
                        discount = %s,
                        amount_after_discount = %s,
                        total_amount = %s
                    WHERE id = %s
                """, [
                    formData.get('title'),
                    formData.get('client_name'),
                    formData.get('contact_person_name'),
                    formData.get('contact_person_number'),
                    formData.get('venue_address'),
                    formData.get('status'),
                    formData.get('crew_type'),
                    formData.get('no_of_container'),
                    formData.get('employee'),
                    formData.get('setup_date'),
                    formData.get('rehearsal_date'),
                    formData.get('show_start_date'),
                    formData.get('show_end_date'),
                    formData.get('total_days'),
                    formData.get('amount_row'),
                    formData.get('discount'),
                    formData.get('amount_after_discount'),
                    formData.get('total_amount'),
                    jobId
                ])

                # Update the job_details table
                for row in rows:
                    jobDetailId = row.get('jobDetailId')
                    category_name = row.get('category_name')
                    equipment_name = row.get('equipment_name')
                    quantity = row.get('quantity')
                    number_of_days = row.get('number_of_days')
                    amount = row.get('amount')

                    cursor.execute("""
                        UPDATE job_details
                        SET category_name = %s,
                            equipment_name = %s,
                            quantity = %s,
                            number_of_days = %s,
                            amount = %s
                        WHERE id = %s
                    """, [category_name, equipment_name, quantity, number_of_days, amount, jobDetailId])

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request method'})


@csrf_exempt
def save_job_details(request):
    if request.method == 'POST':
        job_id = request.POST.get('job_id')
        category_name = request.POST.get('category_name')
        equipment_id = request.POST.get('equipment_id')
        quantity = request.POST.get('quantity')
        number_of_days = request.POST.get('number_of_days')
        amount = request.POST.get('amount')

        try:
            with connection.cursor() as cursor:
                # Fetch the equipment_name based on equipment_id from equipment_list table
                cursor.execute("SELECT equipment_name FROM equipment_list WHERE id = %s", [equipment_id])
                equipment_name = cursor.fetchone()

                if not equipment_name:
                    return JsonResponse({'status': 'error', 'message': 'Equipment not found'}, status=404)

                # Insert the new row into the job_details table
                cursor.execute("""
                    INSERT INTO job_details (job_id, category_name, equipment_name, quantity, number_of_days, amount)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (job_id, category_name, equipment_name[0], quantity, number_of_days, amount))

            return JsonResponse({'status': 'success'}, status=200)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


@csrf_exempt
def delete_job_detail(request):
    if request.method == 'POST':
        job_detail_id = request.POST.get('jobDetailId')

        if not job_detail_id:
            return JsonResponse({'status': 'error', 'message': 'Job detail ID is required'})

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM job_details
                    WHERE id = %s
                """, [job_detail_id])

            return JsonResponse({'status': 'success', 'message': 'Row deleted successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

